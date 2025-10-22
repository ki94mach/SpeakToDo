import logging
import json
from typing import List, Dict, Optional
from openai import OpenAI
import config
from monday_client import MondayClient, AssignablePeopleService

logger = logging.getLogger(__name__)

class TaskExtractor:
    def __init__(self, *, max_owners: int = 500):
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.monday = MondayClient(config.MONDAY_API_TOKEN)
        self.svc = AssignablePeopleService(self.monday)
        self._owners_cache: Dict[int, List[Dict]] = {}   # board_id -> [{id,name,email}]
        self._max_owners = max_owners

        # System prompt for task extraction
        self.system_prompt = """
        You are a task extraction assistant for "SpeakToDo". You analyze a spoken transcript (which may be in Persian/Farsi or mixed languages) and extract only clear, actionable tasks as structured JSON.

        CRITICAL RULES
        1) Always OUTPUT ONLY a JSON array (no prose, no code fences). If no tasks: output [].
        2) Extract only concrete, actionable tasks with a clear action verb (e.g., “Schedule”, “Email”, “Prepare”, “Review”).
        3) Convert vague statements into specific tasks when reasonable.
        4) Ignore greetings, chit-chat, non-task info.
        5) Infer project/context and assignee when stated or strongly implied.
        6) Use absolute dates in ISO "YYYY-MM-DD" when the transcript gives a specific or relative time.
        7) If the transcript is in Persian (Farsi), translate internally and still output tasks IN ENGLISH.
        8) Assume TODAY = 2025-10-21 and TIMEZONE = Asia/Dubai (UTC+04:00) when resolving relative dates (e.g., “Friday” ⇒ 2025-10-24; “tomorrow” ⇒ 2025-10-22; “next week” ⇒ the next Monday of the following week unless a specific day is provided).
        9) OWNER POLICY:
            - If the transcript explicitly or strongly implies an assignee name, try to match it against ALLOWED_OWNERS (a JSON list of {id, name, email}) using case-insensitive comparison. Also compare against the email local-part (before '@') as if it were a name; treat dots/underscores/hyphens as separators. Handle Persian transliteration sensibly.
            - If there is a single clear match, output that **allowed** owner using either their exact "name" or "email" from ALLOWED_OWNERS.
            - If NO clear match exists but an owner name was mentioned, **keep the transcribed owner string exactly as heard**.
            - Only set "owner" to "Me" when the transcript does not mention any person at all.
        10) If project is not specified, infer from context (e.g., “website project”, “budget proposal”) or use a concise context like “General”.

        OUTPUT SCHEMA
        [
        {
            "project_title": "Project name or context",
            "task_title": "Task name/description (imperative)",
            "owner": "Person responsible (or 'Me')",
            "due_date": "YYYY-MM-DD or null"
        }
        ]

        EXTRACTION STEPS
        - Translate to English internally if needed, but DO NOT include the translation in the output.
        - Split the transcript into candidate directives.
        - Keep only items that are tasks (an action someone should do).
        - Normalize task titles to an imperative verb phrase.
        - Resolve relative dates to absolute YYYY-MM-DD using TODAY and TIMEZONE above.
        - Map pronouns: I/me ⇒ "Me"; “Sarah/سارا”, “Ali/علی”, etc. keep proper names in Latin characters where possible.
        - Project/context: prefer explicit project names (“Website”), otherwise infer from repeated nouns/topics; if none, use “General”.

        EDGE CASES
        - “ASAP”, “today”, “by Friday”, “this afternoon” ⇒ map to a date if unambiguous; else use null.
        - Multiple actions in one sentence ⇒ split into separate tasks.
        - Request to “remind”, “follow up”, “send”, “prepare”, “review”, “schedule”, “call”, “update”, “fix”, “deploy”, “report”, etc. are actionable.
        
        EXAMPLES

        Input: "سارا باید تا جمعه بودجه رو مرور کنه و برای مشتری بازخورد بفرسته"
        Output:
        [
        {
            "project_title": "Budget Review",
            "task_title": "Review the budget",
            "owner": "Sarah",
            "due_date": "2025-10-24"
        },
        {
            "project_title": "Budget Review",
            "task_title": "Send feedback to the client",
            "owner": "Sarah",
            "due_date": "2025-10-24"
        }
        ]

        Input: "I need to wrap up the website homepage, schedule a marketing sync for Wednesday, and Ali should prepare the KPI report next week."
        Output:
        [
        {
            "project_title": "Website",
            "task_title": "Finalize the website homepage",
            "owner": "Me",
            "due_date": null
        },
        {
            "project_title": "Website",
            "task_title": "Schedule a marketing sync",
            "owner": "Me",
            "due_date": "2025-10-22"
        },
        {
            "project_title": "KPI Reporting",
            "task_title": "Prepare the KPI report",
            "owner": "Ali",
            "due_date": "2025-10-27"
        }
        ]
        """

    async def extract_tasks(self, text: str, board_id: Optional[int] = None) -> List[Dict]:
        """
        Extract tasks from the given text using OpenAI GPT.
        Optionally pass the Monday board_id to supply ALLOWED_OWNERS from that board's subitems board.
        """
        try:
            logger.info(f"Extracting tasks from text: {text[:100]}...")

            owners_json = None
            if board_id or getattr(config, "MONDAY_BOARD_ID", None):
                owners = await self._get_allowed_owners(board_id)
                if owners:
                    owners_json = json.dumps(owners, ensure_ascii=False)
                    logger.debug(f"Allowed owners for board {board_id or config.MONDAY_BOARD_ID}: "
                                 f"{len(owners)} users")

            messages = [
                {"role": "system", "content": self.system_prompt},
            ]
            if owners_json:
                # Provide ALLOWED_OWNERS as its own system message
                messages.append({
                    "role": "system",
                    "content": f"ALLOWED_OWNERS JSON (each item is {{id,name,email}}):\n{owners_json}"
                })
            messages.append({"role": "user", "content": f"Extract tasks from this text: {text}"})

            response = self.client.chat.completions.create(
                model="gpt-4.1",
                messages=messages,
                temperature=0.3,
                max_tokens=1000
            )

            response_content = response.choices[0].message.content.strip()
            logger.info(f"OpenAI raw response: {response_content}")

            try:
                tasks = json.loads(response_content)
                if not isinstance(tasks, list):
                    logger.warning("Response is not a list; wrapping in array.")
                    tasks = [tasks] if tasks else []
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {e}")
                logger.error(f"Response content: {response_content}")
                tasks = self._fallback_task_extraction(text)

            validated_tasks = self._validate_tasks(tasks)
            logger.info(f"Extracted {len(validated_tasks)} tasks")
            return validated_tasks

        except Exception as e:
            logger.error(f"Error extracting tasks: {e}")
            return self._fallback_task_extraction(text)

    # ----------------------- ALLOWED_OWNERS helpers -----------------------

    async def _get_allowed_owners(self, board_id: Optional[int]) -> List[Dict]:
        """
        Resolve and cache the ALLOWED_OWNERS list (id, name, email) for a board.
        Uses subitems board if present to mirror the People picker UI.
        """
        resolved_board_id = int(board_id or config.MONDAY_BOARD_ID)
        if resolved_board_id in self._owners_cache:
            return self._owners_cache[resolved_board_id]

        # Fetch from Monday and trim to the minimal shape we need
        ppl = await self.svc.fetch_assignable_people(resolved_board_id)
        owners = []
        seen = set()
        for u in ppl[: self._max_owners]:
            uid = int(u.get("id"))
            # De-dup by ID
            if uid in seen:
                continue
            seen.add(uid)
            owners.append({
                "id": uid,
                "name": (u.get("name") or "").strip(),
                "email": (u.get("email") or None)
            })

        self._owners_cache[resolved_board_id] = owners
        return owners

    # -------------------------- validation & fallback --------------------------

    def _validate_tasks(self, tasks: List[Dict]) -> List[Dict]:
        validated_tasks = []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            if 'task_title' not in task or not str(task['task_title']).strip():
                continue
            clean_task = {
                'project_title': str(task.get('project_title', 'General')).strip() or 'General',
                'task_title': str(task['task_title']).strip(),
                'owner': str(task.get('owner', 'Unassigned')).strip() or 'Unassigned',
                'due_date': task.get('due_date')
            }
            if clean_task['due_date'] and not self._is_valid_date(clean_task['due_date']):
                logger.warning(f"Invalid date format: {clean_task['due_date']}; setting to null")
                clean_task['due_date'] = None
            validated_tasks.append(clean_task)
        return validated_tasks

    def _is_valid_date(self, date_string: str) -> bool:
        try:
            from datetime import datetime
            datetime.strptime(date_string, '%Y-%m-%d')
            return True
        except ValueError:
            return False

    def _fallback_task_extraction(self, text: str) -> List[Dict]:
        logger.info("Using fallback task extraction method")
        task_keywords = [
            'need to', 'have to', 'should', 'must', 'call', 'email', 'send',
            'schedule', 'meet', 'review', 'check', 'update', 'create', 'write',
            'plan', 'organize', 'prepare', 'finish', 'complete', 'research'
        ]
        sentences = text.replace('.', '.\n').replace('!', '!\n').replace('?', '?\n').split('\n')
        tasks = []
        for sentence in sentences:
            s = sentence.strip()
            if not s:
                continue
            sl = s.lower()
            if any(k in sl for k in task_keywords):
                t = s
                if t.lower().startswith('i '): t = t[2:]
                if t.lower().startswith('need to '): t = t[8:]
                if t.lower().startswith('have to '): t = t[8:]
                t = t.strip().capitalize()
                if not t.endswith('.'): t += '.'
                tasks.append({
                    'project_title': 'General',
                    'task_title': t,
                    'owner': 'Unassigned',
                    'due_date': None
                })
        return tasks[:10]
