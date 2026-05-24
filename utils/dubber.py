import os
import json
import time
import shutil
import subprocess
import math
import wave
import struct
from pathlib import Path
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List
import yt_dlp
import static_ffmpeg

# Initialize static-ffmpeg to add ffmpeg/ffprobe to the environment path
try:
    static_ffmpeg.add_paths()
except Exception as e:
    print(f"Warning: Could not add static-ffmpeg paths: {e}")

class Segment(BaseModel):
    start: float = Field(description="Start time of the segment in seconds")
    end: float = Field(description="End time of the segment in seconds")
    original_text: str = Field(description="Original transcription in English")
    translation: str = Field(description="Translated text in Portuguese")

class TranscriptionResult(BaseModel):
    segments: List[Segment]

class VideoDubber:
    def __init__(self, api_key: str, workspace_dir: str = ".", model_name: str = "gemini-2.0-flash"):
        self.client = genai.Client(api_key=api_key)
        self.workspace = Path(workspace_dir).absolute()
        self.model_name = model_name
        self.tasks_dir = self.workspace / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def _update_status(self, task_id: str, status: str, progress: int, message: str, error: str = None, segments: list = None, video_url: str = None):
        """Helper to write status updates to disk so the API can read them in real-time."""
        task_file = self.tasks_dir / f"{task_id}.json"
        
        # Load existing data if available to preserve segments or video_url
        data = {}
        if task_file.exists():
            try:
                with open(task_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass

        data.update({
            "task_id": task_id,
            "status": status,
            "progress": progress,
            "message": message,
            "model_name": self.model_name,
            "updated_at": time.time()
        })
        if error:
            data["error"] = error
        elif "error" in data:
            # Clear previous error when status is no longer failed
            del data["error"]
        if segments is not None:
            data["segments"] = segments
        if video_url is not None:
            data["video_url"] = video_url

        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_task_status(self, task_id: str) -> dict:
        task_file = self.tasks_dir / f"{task_id}.json"
        if not task_file.exists():
            return {"status": "not_found", "progress": 0, "message": "Tarefa não encontrada."}
        try:
            with open(task_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return {"status": "error", "progress": 0, "message": f"Erro ao ler status: {str(e)}"}

    def _get_ffmpeg_path(self, name="ffmpeg"):
        # Since static_ffmpeg.add_paths() adds it to environment, we can just use the command name
        return name

    def _get_video_duration(self, video_path: Path) -> float:
        """Get the duration of a video or audio file using ffprobe."""
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)
        ]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"Error getting duration: {e}")
            return 0.0

    def download_youtube_video(self, url: str, temp_dir: Path, cookies: str = "") -> Path:
        """Download YouTube video using yt-dlp."""
        video_output = temp_dir / "original_video.mp4"
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
            'outtmpl': str(video_output),
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://www.youtube.com/',
            }
        }
        
        if cookies.strip():
            cookies_file = temp_dir / "cookies.txt"
            with open(cookies_file, "w", encoding="utf-8") as f:
                f.write(cookies)
            ydl_opts['cookiefile'] = str(cookies_file)
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        if not video_output.exists():
            # Fallback if merger failed or format wasn't found
            ydl_opts['format'] = 'best'
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
        if not video_output.exists():
            raise FileNotFoundError("Falha ao baixar o vídeo do YouTube.")
            
        return video_output

    def extract_audio(self, video_path: Path, temp_dir: Path) -> Path:
        """Extract audio from video file using ffmpeg."""
        audio_path = temp_dir / "extracted_audio.mp3"
        cmd = [
            "ffmpeg", "-i", str(video_path), "-vn",
            "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1",
            "-y", str(audio_path)
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return audio_path

    def transcribe_and_translate(self, audio_path: Path) -> List[dict]:
        """Upload audio to Gemini File API and get transcription + translation."""
        # 1. Upload to File API
        audio_file = self.client.files.upload(file=audio_path)
        
        # Wait for file processing if needed
        while audio_file.state.name == "PROCESSING":
            time.sleep(2)
            audio_file = self.client.files.get(name=audio_file.name)
            
        if audio_file.state.name == "FAILED":
            raise RuntimeError("Falha no processamento do arquivo de áudio pelo Gemini.")
            
        try:
            prompt = """
            Analise o áudio fornecido (pode estar em qualquer idioma).
            Transcreva-o completamente e traduza-o para o português (Brasil) de forma natural e fluida.
            Retorne o resultado estritamente em formato JSON contendo uma lista de segmentos (frases ou pensamentos lógicos do locutor).
            Cada segmento deve ter:
            - "start": tempo inicial em segundos (float)
            - "end": tempo final em segundos (float)
            - "original_text": a transcrição exata no idioma original correspondente a este trecho
            - "translation": a tradução fluida para o português (Brasil) correspondente a este trecho
            
            Certifique-se de que os tempos (start e end) estejam precisamente alinhados com o momento em que as palavras correspondentes são ditas no áudio.
            Divida o áudio em segmentos pequenos (geralmente entre 2 a 8 segundos de duração) para melhor alinhamento na dublagem.
            Se o áudio já estiver em português, retorne o texto original e a mesma tradução.
            """
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[audio_file, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=TranscriptionResult,
                ),
            )
            
            result = json.loads(response.text)
            segments = result.get("segments", [])
            
            # Clean up segments
            cleaned_segments = []
            for i, seg in enumerate(segments):
                cleaned_segments.append({
                    "id": i,
                    "start": float(seg["start"]),
                    "end": float(seg["end"]),
                    "original_text": str(seg["original_text"]),
                    "translation": str(seg["translation"])
                })
                
            return cleaned_segments
            
        finally:
            # Always delete file from Gemini to be clean
            try:
                self.client.files.delete(name=audio_file.name)
            except Exception as e:
                print(f"Error deleting file from Gemini: {e}")

    def generate_voice_segment(self, text: str, voice_name: str, output_path: Path):
        """Generate audio for a single text translation segment using Gemini's response modalities."""
        prompt = f"Diga o seguinte texto em português do Brasil com entonação natural, sem adicionar qualquer comentário ou introdução: {text}"
        
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name
                        )
                    )
                )
            )
        )
        
        # Extract audio bytes from the response parts
        # IMPORTANT: Gemini returns raw 16-bit PCM at 24kHz mono, NOT a WAV file.
        pcm_bytes = None
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                pcm_bytes = part.inline_data.data
                break
                
        if not pcm_bytes:
            raise RuntimeError("Nenhum dado de áudio retornado pelo Gemini para o segmento.")
        
        # Convert raw PCM bytes to a proper WAV file with headers
        # so ffmpeg and audio players can read it correctly.
        with wave.open(str(output_path), 'wb') as wav_file:
            wav_file.setnchannels(1)       # Mono
            wav_file.setsampwidth(2)       # 16-bit = 2 bytes per sample
            wav_file.setframerate(24000)   # 24 kHz sample rate
            wav_file.writeframes(pcm_bytes)

    def process_and_align_audio(self, segments: List[dict], voice_name: str, temp_dir: Path, original_duration: float, ducking: bool = True) -> Path:
        """Generate all segments, speed-correct them, align them on a timeline, and mix with original audio."""
        voice_dir = temp_dir / "voice_segments"
        voice_dir.mkdir(exist_ok=True)
        
        delayed_audios = []
        
        for i, seg in enumerate(segments):
            seg_id = seg["id"]
            start = seg["start"]
            end = seg["end"]
            text = seg["translation"]
            target_duration = end - start
            
            raw_segment_path = voice_dir / f"seg_{seg_id}_raw.wav"
            aligned_segment_path = voice_dir / f"seg_{seg_id}_aligned.wav"
            delayed_segment_path = voice_dir / f"seg_{seg_id}_delayed.wav"
            
            # 1. Generate the raw audio using Gemini voice
            self.generate_voice_segment(text, voice_name, raw_segment_path)
            
            # 2. Get actual duration of the generated audio
            actual_duration = self._get_video_duration(raw_segment_path)
            if actual_duration <= 0:
                actual_duration = target_duration
                
            # 3. Calculate speed ratio to fit within original time slot
            ratio = actual_duration / target_duration if target_duration > 0 else 1.0
            # Clamp the ratio to reasonable bounds for speech naturalness
            ratio = max(0.5, min(2.0, ratio))
            
            # 4. Apply speed correction using ffmpeg atempo
            # Note: atempo filter only accepts values between 0.5 and 100.0
            # For values outside 0.5-2.0, we chain multiple atempo filters
            atempo_filters = []
            remaining = ratio
            while remaining > 2.0:
                atempo_filters.append("atempo=2.0")
                remaining /= 2.0
            while remaining < 0.5:
                atempo_filters.append("atempo=0.5")
                remaining /= 0.5
            atempo_filters.append(f"atempo={remaining}")
            filter_chain = ",".join(atempo_filters)
            
            cmd_speed = [
                "ffmpeg", "-i", str(raw_segment_path),
                "-filter:a", filter_chain,
                "-y", str(aligned_segment_path)
            ]
            subprocess.run(cmd_speed, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            
            # 5. Delay the audio according to the starting timestamp
            # We delay using milliseconds
            delay_ms = int(start * 1000)
            
            # adelay requires a delay for each channel. Since it's a mono/stereo output,
            # we delay both left and right: delay_ms|delay_ms
            cmd_delay = [
                "ffmpeg", "-i", str(aligned_segment_path),
                "-filter_complex", f"adelay={delay_ms}|{delay_ms}",
                "-y", str(delayed_segment_path)
            ]
            subprocess.run(cmd_delay, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            
            delayed_audios.append(delayed_segment_path)

        # 6. Generate silent background audio track of original video's length
        silence_path = temp_dir / "silence.wav"
        cmd_silence = [
            "ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=stereo",
            "-t", str(original_duration), "-y", str(silence_path)
        ]
        subprocess.run(cmd_silence, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        # 7. Mix all delayed audio segments together with the silence track
        # amix merges multiple inputs. 
        # Inputs will be: silence + delayed segments
        # filter_complex: amix=inputs=N:duration=first:dropout_transition=0
        dubbed_audio_only = temp_dir / "dubbed_audio_only.wav"
        
        mix_inputs = [silence_path] + delayed_audios
        cmd_mix = ["ffmpeg"]
        for inp in mix_inputs:
            cmd_mix.extend(["-i", str(inp)])
            
        num_inputs = len(mix_inputs)
        cmd_mix.extend([
            "-filter_complex", f"amix=inputs={num_inputs}:duration=first:dropout_transition=0",
            "-y", str(dubbed_audio_only)
        ])
        subprocess.run(cmd_mix, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        
        # 8. Blend with original audio (ducking) or keep pure dubbed audio
        final_audio = temp_dir / "final_mixed_audio.wav"
        
        # Look for the original audio in multiple possible locations
        # (during initial run it's 'extracted_audio.mp3', during regen it's 'original_audio.mp3')
        original_audio = temp_dir / "extracted_audio.mp3"
        if not original_audio.exists():
            original_audio = temp_dir / "original_audio.mp3"
        
        if ducking and original_audio.exists():
            # Duck original audio to 15% and mix with 100% dubbed audio
            cmd_duck = [
                "ffmpeg", "-i", str(original_audio), "-i", str(dubbed_audio_only),
                "-filter_complex", "[0:a]volume=0.15[bg];[1:a]volume=1.0[fg];[bg][fg]amix=inputs=2:duration=first:dropout_transition=0",
                "-y", str(final_audio)
            ]
            subprocess.run(cmd_duck, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        else:
            final_audio = dubbed_audio_only
            
        return final_audio

    def merge_audio_video(self, video_path: Path, audio_path: Path, output_path: Path) -> Path:
        """Merge final audio track back with the original video track, replacing original audio."""
        cmd = [
            "ffmpeg", "-i", str(video_path), "-i", str(audio_path),
            "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0",
            "-y", str(output_path)
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return output_path

    def run_dubbing_pipeline(self, task_id: str, url: str, voice_name: str, ducking: bool = True, cookies: str = ""):
        """Execute the entire dubbing pipeline from YouTube download to final video."""
        temp_dir = self.workspace / "temp" / task_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        output_dir = self.workspace / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_video_path = output_dir / f"{task_id}_dubbed.mp4"
        
        try:
            # STEP 1: Download Video
            self._update_status(task_id, "processing", 15, "Baixando vídeo do YouTube...")
            original_video = self.download_youtube_video(url, temp_dir, cookies=cookies)
            original_duration = self._get_video_duration(original_video)
            
            # Cache the original video for segment regeneration
            original_cached_video = output_dir / f"{task_id}_original.mp4"
            shutil.copy2(original_video, original_cached_video)
            
            # STEP 2: Extract Audio
            self._update_status(task_id, "processing", 30, "Extraindo áudio original...")
            original_audio = self.extract_audio(original_video, temp_dir)
            
            # STEP 3: Transcribe & Translate (Gemini)
            self._update_status(task_id, "processing", 50, "Transcrevendo e traduzindo o áudio com o Gemini...")
            segments = self.transcribe_and_translate(original_audio)
            self._update_status(task_id, "processing", 60, "Processamento de voz e tradução concluídos.", segments=segments)
            
            # STEP 4: Audio Generation and Stitching
            self._update_status(task_id, "processing", 80, "Gerando voz neural em português para cada segmento...")
            final_audio = self.process_and_align_audio(segments, voice_name, temp_dir, original_duration, ducking=ducking)
            
            # STEP 5: Merge Audio with Video
            self._update_status(task_id, "processing", 95, "Mesclando novo áudio com o vídeo...")
            self.merge_audio_video(original_video, final_audio, output_video_path)
            
            # Success!
            video_url = f"/api/download/{task_id}"
            self._update_status(task_id, "completed", 100, "Dublagem concluída com sucesso!", segments=segments, video_url=video_url)
            
            # Clean up temp folder
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Error cleaning up temp directory: {e}")
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._update_status(task_id, "failed", 100, f"Erro no pipeline: {str(e)}", error=str(e))
            
    def regenerate_single_segment(self, task_id: str, segment_id: int, updated_text: str, voice_name: str, ducking: bool = True):
        """Regenerate a single segment and rebuild the whole video."""
        task_data = self.get_task_status(task_id)
        if task_data.get("status") != "completed":
            raise RuntimeError("Não é possível regenerar segmentos de uma tarefa incompleta.")
            
        segments = task_data.get("segments", [])
        target_segment = None
        for seg in segments:
            if seg["id"] == segment_id:
                target_segment = seg
                break
                
        if not target_segment:
            raise ValueError(f"Segmento {segment_id} não encontrado.")
            
        # Update translation text
        target_segment["translation"] = updated_text
        
        # Save updating status
        self._update_status(task_id, "processing", 80, f"Re-gerando áudio para o segmento {segment_id}...", segments=segments)
        
        temp_dir = self.workspace / "temp" / f"regen_{task_id}_{segment_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        output_video_path = self.workspace / "output" / f"{task_id}_dubbed.mp4"
        
        try:
            # We need the original video. But wait, we cleaned up the temp_dir!
            # If we don't have the original video, how do we rebuild?
            # Actually, to make segment regeneration robust, we can copy the original video to our output dir as `{task_id}_original.mp4` during the first run so it's always cached, or keep it in temp.
            # Let's check: if `{task_id}_original.mp4` doesn't exist, we can't do regeneration easily without downloading it again.
            # Let's adjust the first run to save the original video in `output/{task_id}_original.mp4`!
            # That's a highly intelligent improvement!
            original_cached_video = self.workspace / "output" / f"{task_id}_original.mp4"
            if not original_cached_video.exists():
                raise FileNotFoundError("Vídeo original em cache não encontrado. Não é possível regenerar.")
                
            original_duration = self._get_video_duration(original_cached_video)
            
            # Extract original audio if it's not cached
            original_audio = temp_dir / "original_audio.mp3"
            cmd_audio = [
                "ffmpeg", "-i", str(original_cached_video), "-vn",
                "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1",
                "-y", str(original_audio)
            ]
            subprocess.run(cmd_audio, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            
            # Generate the new audio track
            final_audio = self.process_and_align_audio(segments, voice_name, temp_dir, original_duration, ducking=ducking)
            
            # Merge back
            self.merge_audio_video(original_cached_video, final_audio, output_video_path)
            
            video_url = f"/api/download/{task_id}"
            self._update_status(task_id, "completed", 100, "Segmento regenerado e vídeo atualizado com sucesso!", segments=segments, video_url=video_url)
            
            # Clean up regen temp folder
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
                
        except Exception as e:
            self._update_status(task_id, "completed", 100, "Concluído com erro ao regenerar segmento.", segments=segments, error=str(e))
            raise e
