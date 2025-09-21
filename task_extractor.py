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
        You are a task extraction assistant. Your job is to analyze text and extract actionable tasks from it.

        Rules:
        1. Extract only clear, actionable tasks from the input text
        2. Each task should be specific and actionable
        3. Convert vague statements into concrete tasks when possible
        4. Ignore greetings, pleasantries, and non-task content
        5. If no tasks are found, return an empty list
        6. Each task should have a clear action verb

        Return the tasks as a JSON array of objects with the following structure:
        [
        {
            "name": "Task name/description",
            "priority": "High" | "Medium" | "Low",
            "category": "Meeting" | "Call" | "Email" | "Research" | "Development" | "Planning" | "Review" | "Other",
            "estimated_duration": "15 minutes" | "30 minutes" | "1 hour" | "2 hours" | "Half day" | "Full day" | "Multiple days"
        }
        ]

        Examples:
        Input: "I need to call John about the project and schedule a meeting with the marketing team"
        Output: [
        {
            "name": "Call John about the project",
            "priority": "High",
            "category": "Call",
            "estimated_duration": "30 minutes"
        },
        {
            "name": "Schedule meeting with marketing team",
            "priority": "Medium",
            "category": "Meeting",
            "estimated_duration": "15 minutes"
        }
        ]

        Input: "Review the budget proposal and send feedback to Sarah"
        Output: [
        {
            "name": "Review budget proposal",
            "priority": "High",
            "category": "Review",
            "estimated_duration": "1 hour"
        },
        {
            "name": "Send feedback to Sarah about budget proposal",
            "priority": "Medium",
            "category": "Email",
            "estimated_duration": "15 minutes"
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
                model="gpt-3.5-turbo",
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
            if 'name' not in task or not task['name'].strip():
                continue
            
            # Clean and validate the task
            clean_task = {
                'name': task['name'].strip(),
                'priority': task.get('priority', 'Medium'),
                'category': task.get('category', 'Other'),
                'estimated_duration': task.get('estimated_duration', '30 minutes')
            }
            
            # Validate priority
            if clean_task['priority'] not in ['High', 'Medium', 'Low']:
                clean_task['priority'] = 'Medium'
            
            # Validate category
            valid_categories = ['Meeting', 'Call', 'Email', 'Research', 'Development', 'Planning', 'Review', 'Other']
            if clean_task['category'] not in valid_categories:
                clean_task['category'] = 'Other'
            
            validated_tasks.append(clean_task)
        
        return validated_tasks
    
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
                task_name = sentence
                if task_name.lower().startswith('i '):
                    task_name = task_name[2:]  # Remove "I "
                if task_name.lower().startswith('need to '):
                    task_name = task_name[8:]  # Remove "need to "
                if task_name.lower().startswith('have to '):
                    task_name = task_name[8:]  # Remove "have to "
                
                task_name = task_name.strip().capitalize()
                if not task_name.endswith('.'):
                    task_name += '.'
                
                tasks.append({
                    'name': task_name,
                    'priority': 'Medium',
                    'category': 'Other',
                    'estimated_duration': '30 minutes'
                })
        
        return tasks[:10]  # Limit to 10 tasks maximum

# Example usage and testing
if __name__ == "__main__":
    import asyncio
    
    async def test_task_extractor():
        extractor = TaskExtractor()
        
        # Test cases
        test_texts = [
            "I need to call John about the project and schedule a meeting with the marketing team for next week",
            "Review the budget proposal, send feedback to Sarah, and prepare the presentation for Monday",
            "Hello, how are you? The weather is nice today.",
            "Research competitors, update the website, and organize the team lunch"
        ]
        
        for text in test_texts:
            print(f"\nInput: {text}")
            tasks = await extractor.extract_tasks(text)
            print(f"Extracted {len(tasks)} tasks:")
            for task in tasks:
                print(f"  - {task['name']} [{task['priority']}] ({task['category']})")
    
    asyncio.run(test_task_extractor())
