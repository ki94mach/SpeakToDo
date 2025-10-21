import logging
import json
from typing import List, Dict
from openai import OpenAI
import config

logger = logging.getLogger(__name__)

class TaskExtractor:
    def __init__(self):
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        
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
        9) If assignee is not specified, set "owner" to "Me".
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

    async def extract_tasks(self, text: str) -> List[Dict]:
        """
        Extract tasks from the given text using OpenAI GPT.
        
        Args:
            text (str): The input text to extract tasks from
            
        Returns:
            List[Dict]: List of extracted tasks with metadata
        """
        try:
            logger.info(f"Extracting tasks from text: {text[:100]}...")
            
            # Call OpenAI API for task extraction
            response = self.client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"Extract tasks from this text: {text}"}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            # Parse the response
            response_content = response.choices[0].message.content.strip()
            logger.info(f"OpenAI response: {response_content}")
            
            # Try to parse JSON response
            try:
                tasks = json.loads(response_content)
                if not isinstance(tasks, list):
                    logger.warning("Response is not a list, wrapping in array")
                    tasks = [tasks] if tasks else []
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(f"Response content: {response_content}")
                
                # Fallback: try to extract tasks using simple parsing
                tasks = self._fallback_task_extraction(text)
            
            # Validate and clean tasks
            validated_tasks = self._validate_tasks(tasks)
            
            logger.info(f"Successfully extracted {len(validated_tasks)} tasks")
            return validated_tasks
            
        except Exception as e:
            logger.error(f"Error extracting tasks: {e}")
            # Fallback to simple extraction
            return self._fallback_task_extraction(text)
    
    def _validate_tasks(self, tasks: List[Dict]) -> List[Dict]:
        """
        Validate and clean the extracted tasks.
        
        Args:
            tasks (List[Dict]): Raw tasks from extraction
            
        Returns:
            List[Dict]: Validated and cleaned tasks
        """
        validated_tasks = []
        
        for task in tasks:
            if not isinstance(task, dict):
                continue
                
            # Ensure required fields exist
            if 'task_title' not in task or not task['task_title'].strip():
                continue
            
            # Clean and validate the task
            clean_task = {
                'project_title': task.get('project_title', 'General').strip(),
                'task_title': task['task_title'].strip(),
                'owner': task.get('owner', 'Unassigned').strip(),
                'due_date': task.get('due_date')
            }
            
            # Validate due_date format if provided
            if clean_task['due_date'] and not self._is_valid_date(clean_task['due_date']):
                logger.warning(f"Invalid date format: {clean_task['due_date']}, setting to null")
                clean_task['due_date'] = None
            
            validated_tasks.append(clean_task)
        
        return validated_tasks
    
    def _is_valid_date(self, date_string: str) -> bool:
        """
        Check if the date string is in valid YYYY-MM-DD format.
        
        Args:
            date_string (str): Date string to validate
            
        Returns:
            bool: True if valid date format
        """
        try:
            from datetime import datetime
            datetime.strptime(date_string, '%Y-%m-%d')
            return True
        except ValueError:
            return False
    
    def _fallback_task_extraction(self, text: str) -> List[Dict]:
        """
        Fallback method for task extraction using simple keyword matching.
        
        Args:
            text (str): Input text
            
        Returns:
            List[Dict]: Simple extracted tasks
        """
        logger.info("Using fallback task extraction method")
        
        # Common task indicators
        task_keywords = [
            'need to', 'have to', 'should', 'must', 'call', 'email', 'send',
            'schedule', 'meet', 'review', 'check', 'update', 'create', 'write',
            'plan', 'organize', 'prepare', 'finish', 'complete', 'research'
        ]
        
        sentences = text.replace('.', '.\n').replace('!', '!\n').replace('?', '?\n').split('\n')
        tasks = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # Check if sentence contains task keywords
            sentence_lower = sentence.lower()
            if any(keyword in sentence_lower for keyword in task_keywords):
                # Clean up the sentence to make it more task-like
                task_title = sentence
                if task_title.lower().startswith('i '):
                    task_title = task_title[2:]  # Remove "I "
                if task_title.lower().startswith('need to '):
                    task_title = task_title[8:]  # Remove "need to "
                if task_title.lower().startswith('have to '):
                    task_title = task_title[8:]  # Remove "have to "
                
                task_title = task_title.strip().capitalize()
                if not task_title.endswith('.'):
                    task_title += '.'
                
                tasks.append({
                    'project_title': 'General',
                    'task_title': task_title,
                    'owner': 'Unassigned',
                    'due_date': None
                })
        
        return tasks[:10]  # Limit to 10 tasks maximum

# Example usage and testing
if __name__ == "__main__":
    import asyncio
    
    async def test_task_extractor():
        extractor = TaskExtractor()
        
        # Test cases
        test_texts = [
            "I need to call John about the website project and schedule a meeting with the marketing team for next week",
            "Sarah should review the budget proposal by Friday and send feedback to the client",
            "Hello, how are you? The weather is nice today.",
            "Research competitors for the mobile app project, update the website, and organize the team lunch"
        ]
        
        for text in test_texts:
            print(f"\nInput: {text}")
            tasks = await extractor.extract_tasks(text)
            print(f"Extracted {len(tasks)} tasks:")
            for task in tasks:
                print(f"  - Project: {task['project_title']}")
                print(f"    Task: {task['task_title']}")
                print(f"    Owner: {task['owner']}")
                print(f"    Due Date: {task['due_date'] or 'Not specified'}")
                print()
    
    asyncio.run(test_task_extractor())
