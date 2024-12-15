from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import yt_dlp
import os
import logging
from datetime import datetime
import tempfile
import re

app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "Accept"],
        "expose_headers": ["Content-Type", "Content-Disposition"]
    }
})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def sanitize_filename(filename):
    # 移除非法字元
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # 限制長度
    return filename[:200]

@app.route('/api/video-info', methods=['POST'])
def get_video_info():
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': '請提供YouTube網址'}), 400

        logger.info(f"Getting info for URL: {url}")

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'bestvideo+bestaudio/best',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # 處理影片格式
            formats = []
            for f in info['formats']:
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':  # 只選擇有影片和音訊的格式
                    format_info = {
                        'format_id': f['format_id'],
                        'ext': f['ext'],
                        'resolution': f.get('resolution', 'N/A'),
                        'filesize': f.get('filesize', 0),
                        'filesize_approx': f.get('filesize_approx', 0),
                    }
                    formats.append(format_info)

            # 取得影片ID用於嵌入
            video_id = info.get('id', '')
            
            video_info = {
                'title': info.get('title', ''),
                'duration': info.get('duration', 0),
                'views': info.get('view_count', 0),
                'video_id': video_id,
                'formats': formats,
                'author': info.get('uploader', ''),
                'publish_date': info.get('upload_date', '')
            }

            return jsonify(video_info)

    except Exception as e:
        logger.error(f"Error getting video info: {str(e)}")
        return jsonify({'error': f'獲取影片信息失敗: {str(e)}'}), 400

@app.route('/api/download', methods=['GET'])
def download_video():
    try:
        url = request.args.get('url')
        format_id = request.args.get('format_id')
        format_type = request.args.get('format', 'mp4')
        
        if not url:
            return jsonify({'error': '請提供YouTube網址'}), 400

        logger.info(f"Starting download for URL: {url}")

        # 創建臨時目錄
        temp_dir = tempfile.mkdtemp()

        # 先獲取影片資訊以取得標題
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = sanitize_filename(info['title'])
            output_file = os.path.join(temp_dir, f'{title}.{format_type}')

        # yt-dlp 配置
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'outtmpl': output_file,
        }

        if format_type == 'mp3':
            ydl_opts.update({
                'format': 'bestaudio',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            ydl_opts.update({
                'format': format_id if format_id else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'merge_output_format': 'mp4',
            })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                raise Exception('下載失敗：檔案不存在或大小為0')

            return send_file(
                output_file,
                as_attachment=True,
                download_name=f"{title}.{format_type}",
                mimetype='audio/mpeg' if format_type == 'mp3' else 'video/mp4'
            )

        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            raise Exception(f'下載過程發生錯誤: {str(e)}')

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 400

    finally:
        try:
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                for f in os.listdir(temp_dir):
                    os.remove(os.path.join(temp_dir, f))
                os.rmdir(temp_dir)
        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
