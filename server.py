import os
import yt_dlp
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import subprocess
import re
import uuid

app = Flask(__name__)
app.secret_key = str(uuid.uuid4())  # 세션을 위한 비밀 키

# 사용자 정보를 저장할 간단한 딕셔너리
users = {}

# 다운로드 디렉토리 설정
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# FFmpeg 설치 경로 (예시)
FFMPEG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'ffmpeg_bin', 'ffmpeg.exe'))

# 경로 확인용 디버깅 코드
if not os.path.exists(FFMPEG_PATH):
    raise FileNotFoundError(f"FFmpeg 실행 파일을 찾을 수 없습니다: {FFMPEG_PATH}")

print(f"FFmpeg 경로: {FFMPEG_PATH}")
 # FFmpeg 경로

# 사용자 이름과 비밀번호 규칙 검사 함수
def is_valid_username(username):
    username_pattern = r'^[a-zA-Z0-9][a-zA-Z0-9\.]{5,29}[a-zA-Z0-9]$'
    return re.match(username_pattern, username) is not None

def is_valid_password(password):
    password_pattern = r'^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,16}$'
    return re.match(password_pattern, password) is not None

# 사용자 다운로드 기록을 저장하는 함수
def save_download_info(username, video_title, thumbnail_url, format_choice, video_url):
    if username not in users:
        users[username] = {"downloads": []}
    users[username]["downloads"].append({
        "video_title": video_title,
        "thumbnail_url": thumbnail_url,
        "format": format_choice,
        "video_url": video_url  # 유튜브 링크 추가
    })

@app.route('/')
def index():
    username = session.get('username')
    return render_template('index.html', username=username)



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username not in users:
            flash("Username doesn't exist!", 'error')
        elif not check_password_hash(users[username]['password'], password):
            flash("Incorrect password!", 'error')
        else:
            session['username'] = username
            return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("You have been logged out.", 'success')
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if not is_valid_username(username):
            flash("Invalid username. Please follow the username rules.", 'error')
        elif not is_valid_password(password):
            flash("Invalid password. Please follow the password rules.", 'error')
        elif username in users:
            flash("Username already exists. Choose another one.", 'error')
        else:
            hashed_password = generate_password_hash(password)
            users[username] = {'password': hashed_password, 'downloads': []}
            flash("Registration successful! Please log in.", 'success')
            return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/profile')
def profile():
    if 'username' not in session:
        flash("You must be logged in to view your profile.", 'error')
        return redirect(url_for('login'))
    
    username = session.get('username')
    user_data = users.get(username, {})
    # 최근 다운로드된 영상 목록 가져오기
    downloads = user_data.get('downloads', [])
    return render_template('profile.html', username=username, downloads=downloads)

@app.route('/delete_account')
def delete_account():
    if 'username' not in session:
        flash("You must be logged in to delete your account.", 'error')
        return redirect(url_for('login'))

    username = session.get('username')
    del users[username]  # 해당 사용자 정보 삭제
    session.pop('username', None)  # 로그아웃 처리
    flash("Your account has been deleted.", 'success')
    return redirect(url_for('index'))

@app.route('/delete_download/<int:index>', methods=['GET'])
def delete_download(index):
    if 'username' not in session:
        flash("You must be logged in to delete downloads.", 'error')
        return redirect(url_for('login'))

    username = session.get('username')
    user_data = users.get(username, {})
    
    if 0 <= index < len(user_data.get('downloads', [])):
        # 다운로드 목록에서 해당 항목 삭제
        del user_data['downloads'][index]
        flash("Download entry has been deleted.", 'success')
    else:
        flash("Invalid download entry.", 'error')

    return redirect(url_for('profile'))

# 음원 다운로드 및 변환
@app.route('/download', methods=['POST'])
def download():
    url = request.form['url']  # 입력된 YouTube URL
    format_choice = request.form['format']  # 선택한 오디오 형식
    
    if 'username' not in session:
        # 로그아웃 상태일 때도 다운로드를 처리하려면 여기를 수정
        username = "guest"  # 세션이 없으면 'guest'로 처리하거나, 별도의 처리 로직 추가
    else:
        username = session['username']
    
    try:
        # yt-dlp 옵션 설정
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'extractaudio': True,
            'prefer_ffmpeg': True,
            'noplaylist': True,
            'no_post_overwrites': True,
            'quiet': True,
            'no_warnings': True,
        }

        if format_choice == 'mp3_320':
            ydl_opts['audioquality'] = 0
        elif format_choice == 'mp3_192':
            ydl_opts['audioquality'] = 1
        elif format_choice == 'wav':
            ydl_opts['format'] = 'bestaudio/best'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_title = info_dict.get('title', 'Unknown')
            thumbnail_url = info_dict.get('thumbnail', ' ')
            if 'username' in session:
                save_download_info(session['username'], video_title, thumbnail_url, format_choice, url)

        # 다운로드한 파일 찾기
        filename = os.listdir(DOWNLOAD_DIR)[-1]  # 가장 최근에 다운로드한 파일
        file_path = os.path.join(DOWNLOAD_DIR, filename)

        # mp3로 변환하기
        if filename.endswith('.webm') or filename.endswith('.m4a'):
            if format_choice.startswith('mp3'):
                mp3_filename = filename.replace('.webm', '.mp3').replace('.m4a', '.mp3')
                mp3_path = os.path.join(DOWNLOAD_DIR, mp3_filename)
                subprocess.run([FFMPEG_PATH, '-y', '-i', file_path, '-vn', '-ar', '44100', '-ac', '2', '-ab', '320k', '-f', 'mp3', mp3_path])
                os.remove(file_path)
                filename = mp3_filename
            elif format_choice == 'wav':
                wav_filename = filename.replace('.webm', '.wav').replace('.m4a', '.wav')
                wav_path = os.path.join(DOWNLOAD_DIR, wav_filename)
                subprocess.run([FFMPEG_PATH, '-y', '-i', file_path, wav_path])
                os.remove(file_path)
                filename = wav_filename

        return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)
    except Exception as e:
        flash(f"Error: {e}", 'error')
        return redirect(url_for('index'))

@app.route('/redirect_video/<path:video_url>')
def redirect_video(video_url):
    return redirect(video_url)

if __name__ == "__main__":
    app.run(debug=True)
