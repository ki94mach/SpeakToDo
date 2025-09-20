import logging
import os
from openai import OpenAI
from pydub import AudioSegment
import config

logger = logging.getLogger(__name__)

class VoiceToText:
    def __init__(self):
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
    
    def convert_ogg_to_mp3(self, ogg_path: str) -> str:
        """Convert OGG file to MP3 format for better compatibility."""
        try:
            # Load OGG file
            audio = AudioSegment.from_ogg(ogg_path)
            
            # Convert to MP3
            mp3_path = ogg_path.replace('.ogg', '.mp3')
            audio.export(mp3_path, format="mp3")
            
            logger.info(f"Converted {ogg_path} to {mp3_path}")
            return mp3_path
            
        except Exception as e:
            logger.error(f"Error converting OGG to MP3: {e}")
            # If conversion fails, try to use the original file
            return ogg_path
    
    async def convert_to_text(self, audio_file_path: str) -> str:
        """
        Convert audio file to text using OpenAI Whisper API.
        
        Args:
            audio_file_path (str): Path to the audio file
            
        Returns:
            str: Transcribed text
        """
        try:
            # Convert OGG to MP3 if needed
            if audio_file_path.endswith('.ogg'):
                audio_file_path = self.convert_ogg_to_mp3(audio_file_path)
            
            # Open and transcribe the audio file
            with open(audio_file_path, 'rb') as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            
            logger.info(f"Successfully transcribed audio: {transcript[:100]}...")
            
            # Clean up converted MP3 file if it was created
            if audio_file_path.endswith('.mp3') and audio_file_path != audio_file_path.replace('.mp3', '.ogg'):
                if os.path.exists(audio_file_path):
                    os.remove(audio_file_path)
            
            return transcript.strip()
            
        except Exception as e:
            logger.error(f"Error converting voice to text: {e}")
            raise Exception(f"Failed to convert voice to text: {str(e)}")

    async def convert_to_text_with_google(self, audio_file_path: str) -> str:
        """
        Alternative method using Google Speech Recognition API.
        This is a fallback option if OpenAI Whisper is not available.
        
        Args:
            audio_file_path (str): Path to the audio file
            
        Returns:
            str: Transcribed text
        """
        try:
            import speech_recognition as sr
            
            # Convert OGG to WAV for speech_recognition compatibility
            if audio_file_path.endswith('.ogg'):
                audio = AudioSegment.from_ogg(audio_file_path)
                wav_path = audio_file_path.replace('.ogg', '.wav')
                audio.export(wav_path, format="wav")
                audio_file_path = wav_path
            
            # Initialize recognizer
            recognizer = sr.Recognizer()
            
            # Load audio file
            with sr.AudioFile(audio_file_path) as source:
                audio_data = recognizer.record(source)
            
            # Recognize speech using Google Speech Recognition
            if config.GOOGLE_SPEECH_API_KEY:
                text = recognizer.recognize_google(audio_data, key=config.GOOGLE_SPEECH_API_KEY)
            else:
                text = recognizer.recognize_google(audio_data)
            
            logger.info(f"Successfully transcribed audio with Google: {text[:100]}...")
            
            # Clean up temporary WAV file
            if audio_file_path.endswith('.wav'):
                if os.path.exists(audio_file_path):
                    os.remove(audio_file_path)
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"Error converting voice to text with Google: {e}")
            raise Exception(f"Failed to convert voice to text with Google: {str(e)}")

# Example usage and testing
if __name__ == "__main__":
    import asyncio
    
    async def test_voice_to_text():
        converter = VoiceToText()
        
        # This would be used with an actual audio file
        # text = await converter.convert_to_text("test_audio.ogg")
        # print(f"Transcribed text: {text}")
        
        print("VoiceToText component initialized successfully!")
    
    asyncio.run(test_voice_to_text())
