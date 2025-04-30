# import asyncio
# import sys
# from io import BytesIO

# import torch

# import librosa


# https://github.com/fumiama/Retrieval-based-Voice-Conversion-WebUI/blob/main/config.py#L43-L55  # noqa
# def has_mps() -> bool:
#     if sys.platform != "darwin":
#         return False
#     else:
#         if not getattr(torch, 'has_mps', False):
#             return False
#
#         try:
#             torch.zeros(1).to(torch.device("mps"))
#             return True
#         except Exception:
#             return False

#
# def is_half(device: str) -> bool:
#     if not device.startswith('cuda'):
#         return False
#     else:
#         gpu_name = torch.cuda.get_device_name(
#             int(device.split(':')[-1])
#         ).upper()
#
#         # ...regex?
#         if (
#             ('16' in gpu_name and 'V100' not in gpu_name)
#             or 'P40' in gpu_name
#             or '1060' in gpu_name
#             or '1070' in gpu_name
#             or '1080' in gpu_name
#         ):
#             return False
#
#     return True

#
#
# async def call_edge_tts(speaker_name: str, text: str):
#     tts_com = edge_tts.Communicate(text, speaker_name)
#     tts_raw = b''
#
#     # Stream TTS audio to bytes
#     async for chunk in tts_com.stream():
#         if chunk['type'] == 'audio':
#             tts_raw += chunk['data']
#
#     # Convert mp3 stream to wav
#     ffmpeg_proc = await asyncio.create_subprocess_exec(
#         'ffmpeg',
#         '-f', 'mp3',
#         '-i', '-',
#         '-f', 'wav',
#         '-loglevel', 'error',
#         '-',
#         stdin=asyncio.subprocess.PIPE,
#         stdout=asyncio.subprocess.PIPE
#     )
#     (tts_wav, _) = await ffmpeg_proc.communicate(tts_raw)
#
#     return librosa.load(BytesIO(tts_wav))

#
# async def call_edge_tts_config(speaker_name: str, text: str, rate: str, volume: str):
#     tts_com = edge_tts.Communicate(text=text, voice=speaker_name, rate=rate, volume=volume)
#     tts_raw = b''
#
#     # Stream TTS audio to bytes
#     async for chunk in tts_com.stream():
#         if chunk['type'] == 'audio':
#             tts_raw += chunk['data']
#
#     # Convert mp3 stream to wav
#     ffmpeg_proc = await asyncio.create_subprocess_exec(
#         'ffmpeg',
#         '-f', 'mp3',
#         '-i', '-',
#         '-f', 'wav',
#         '-loglevel', 'error',
#         '-',
#         stdin=asyncio.subprocess.PIPE,
#         stdout=asyncio.subprocess.PIPE
#     )
#     (tts_wav, _) = await ffmpeg_proc.communicate(tts_raw)
#
#     return librosa.load(BytesIO(tts_wav))
