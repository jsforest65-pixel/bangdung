import streamlit as st
import os
import subprocess
import tempfile
import asyncio
from pathlib import Path
from pydub import AudioSegment
import edge_tts

st.set_page_config(page_title="숏츠 생성기", layout="wide", initial_sidebar_state="collapsed")

# 커스텀 CSS
st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
    .main { padding: 2rem; }
    h1 { color: white; text-align: center; }
    .stButton>button { width: 100%; height: 50px; font-size: 18px; }
</style>
""", unsafe_allow_html=True)

st.title("📱 숏츠 생성기 (9:16)")
st.markdown("**대본 → 숏츠 영상 자동 생성**", unsafe_allow_html=False)

# 레이아웃
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📝 대본 입력")
    script = st.text_area(
        "대본을 입력하세요 (줄바꿈으로 구분):",
        height=200,
        placeholder="예시:\n안녕하세요\n오늘은 특별한 날입니다\n감사합니다",
        label_visibility="collapsed"
    )

with col2:
    st.subheader("⚙️ 설정")
    font_size = st.slider("글자 크기", 30, 80, 50)
    line_duration = st.slider("줄당 시간(초)", 1.0, 5.0, 2.5)
    bg_color = st.color_picker("배경색", "#000000")
    text_color = st.color_picker("글자색", "#FFFFFF")
    voice_speed = st.slider("음성속도", 0.5, 2.0, 1.0)

# 생성 버튼
if st.button("🎬 숏츠 생성", use_container_width=True):
    if not script or not script.strip():
        st.error("❌ 대본을 입력해주세요")
    else:
        lines = [line.strip() for line in script.split("\n") if line.strip()]

        progress_container = st.container()

        with progress_container:
            progress_bar = st.progress(0)
            status_text = st.empty()

            try:
                temp_dir = tempfile.mkdtemp()
                audio_files = []

                # 1. TTS 음성 생성
                status_text.text("📢 음성 생성 중...")
                progress_bar.progress(10)

                async def generate_audio():
                    for i, line in enumerate(lines):
                        # 음성 속도 계산 (1.0 = 0%, 2.0 = +50%, 0.5 = -50%)
                        rate_percent = int((voice_speed - 1.0) * 100)
                        rate_str = f"+{rate_percent}%" if rate_percent >= 0 else f"{rate_percent}%"

                        communicate = edge_tts.Communicate(
                            text=line,
                            voice="ko-KR-SunHiNeural",
                            rate=rate_str
                        )
                        audio_file = os.path.join(temp_dir, f"audio_{i}.mp3")
                        await communicate.save(audio_file)
                        audio_files.append(audio_file)
                        progress_bar.progress(10 + int((i + 1) / len(lines) * 20))

                try:
                    asyncio.run(generate_audio())
                except Exception as e:
                    st.warning(f"⚠️ TTS 오류: {str(e)[:100]}")
                    for i in range(len(lines)):
                        audio_file = os.path.join(temp_dir, f"audio_{i}.mp3")
                        silent = AudioSegment.silent(duration=int(line_duration * 1000))
                        silent.export(audio_file, format="mp3")
                        audio_files.append(audio_file)

                # 2. 자막 파일 생성 (SRT 형식)
                status_text.text("📝 자막 생성 중...")
                progress_bar.progress(35)

                srt_path = os.path.join(temp_dir, "subtitles.srt")
                current_time = 0

                with open(srt_path, 'w', encoding='utf-8') as f:
                    for i, line in enumerate(lines):
                        try:
                            audio = AudioSegment.from_mp3(audio_files[i])
                            duration = len(audio) / 1000.0
                        except:
                            duration = line_duration

                        start_ms = int(current_time * 1000)
                        end_ms = int((current_time + duration) * 1000)

                        start_str = f"{int(start_ms//3600000):02d}:{int((start_ms%3600000)//60000):02d}:{int((start_ms%60000)//1000):02d},{start_ms%1000:03d}"
                        end_str = f"{int(end_ms//3600000):02d}:{int((end_ms%3600000)//60000):02d}:{int((end_ms%60000)//1000):02d},{end_ms%1000:03d}"

                        f.write(f"{i+1}\n{start_str} --> {end_str}\n{line}\n\n")
                        current_time += duration

                # 3. 음성 병합
                status_text.text("🔗 음성 병합 중...")
                progress_bar.progress(50)

                concat_list = os.path.join(temp_dir, "concat.txt")
                with open(concat_list, 'w') as f:
                    for audio_file in audio_files:
                        f.write(f"file '{audio_file}'\n")

                merged_audio = os.path.join(temp_dir, "merged_audio.mp3")
                cmd = [
                    "ffmpeg", "-f", "concat", "-safe", "0",
                    "-i", concat_list, "-c", "copy", merged_audio, "-y"
                ]
                subprocess.run(cmd, capture_output=True, check=True)

                # 4. 최종 영상 생성 (9:16 = 1080x1920)
                status_text.text("🎬 최종 영상 생성 중...")
                progress_bar.progress(70)

                output_path = os.path.join(temp_dir, "output.mp4")
                bg_hex = bg_color.lstrip('#')

                # RGB를 BGR로 변환 (FFmpeg는 BGR 사용)
                bg_bgr = bg_hex[4:6] + bg_hex[2:4] + bg_hex[0:2]
                text_rgb = text_color.lstrip('#')
                text_bgr = text_rgb[4:6] + text_rgb[2:4] + text_rgb[0:2]

                cmd = [
                    "ffmpeg",
                    "-f", "lavfi", "-i", f"color=0x{bg_bgr}:s=1080x1920:d=0",
                    "-i", merged_audio,
                    "-vf", f"subtitles={srt_path}:force_style='FontSize={font_size},FontName=Arial,PrimaryColour=&H{text_bgr}&,BorderStyle=3,Outline=2,Shadow=2'",
                    "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                    "-c:a", "aac", "-b:a", "128k",
                    output_path, "-y"
                ]

                result = subprocess.run(cmd, capture_output=True, text=True)
                progress_bar.progress(95)

                if result.returncode != 0:
                    st.error(f"❌ FFmpeg 오류: {result.stderr[:200]}")
                else:
                    # 5. 완료
                    progress_bar.progress(100)
                    status_text.text("✅ 완료!")

                    # 영상 표시
                    st.video(output_path)

                    # 다운로드
                    with open(output_path, "rb") as f:
                        st.download_button(
                            label="📥 숏츠 다운로드",
                            data=f.read(),
                            file_name="shorts.mp4",
                            mime="video/mp4",
                            use_container_width=True
                        )

                    # 파일 정보
                    file_size = os.path.getsize(output_path) / (1024*1024)
                    st.success(f"파일 크기: {file_size:.1f}MB")

                # 정리
                import shutil
                shutil.rmtree(temp_dir)

            except Exception as e:
                st.error(f"❌ 오류: {str(e)}")
                progress_bar.progress(0)

# 사용 가이드
with st.expander("💡 사용 가이드"):
    st.markdown("""
    **1. 대본 입력**
    - 한 줄씩 하나의 자막으로 표시됩니다
    - 줄바꿈으로 구분하면 자동 분할됩니다

    **2. 설정**
    - **글자 크기**: 자막 글씨 크기 조절
    - **줄당 시간**: 한 줄이 표시되는 시간
    - **배경색/글자색**: 색상 선택
    - **음성속도**: TTS 음성 재생 속도

    **3. 생성**
    - "숏츠 생성" 버튼 클릭
    - 약 1-2분 소요
    - MP4 파일로 다운로드

    **포맷:**
    - 해상도: 1080x1920 (9:16 세로)
    - 용도: 숏츠, 릴스, 틱톡, 쇼츠
    """)

st.markdown("---")
st.caption("🚀 대본만 있으면 숏츠 완성!")
