from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
import re
import secrets
from datetime import datetime
from urllib.parse import quote

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# كلمة مرور الأدمن
ADMIN_PASSWORD = "z3z3"
DB_NAME = "videos.db"

# تحسينات قاعدة البيانات
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            platform TEXT,
            embed_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.commit()

def insert_video(name, url, platform, embed_url):
    with get_db_connection() as conn:
        try:
            conn.execute("""
                INSERT INTO videos (name, url, platform, embed_url) 
                VALUES (?, ?, ?, ?)
            """, (name, url, platform, embed_url))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

def get_videos():
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT id, name, url, platform, embed_url, created_at
            FROM videos 
            ORDER BY created_at DESC
        """)
        return cursor.fetchall()

def get_video_by_id(video_id):
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT * FROM videos WHERE id = ?
        """, (video_id,))
        return cursor.fetchone()

def delete_all_videos():
    with get_db_connection() as conn:
        conn.execute("DELETE FROM videos")
        conn.commit()

def delete_video(video_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        conn.commit()

def make_embed(url):
    # YouTube
    yt_patterns = [
        r"(?:v=|be/|shorts/)([\w-]{11})",
        r"youtube\.com/embed/([\w-]{11})",
        r"youtu\.be/([\w-]{11})"
    ]
    
    for pattern in yt_patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            return f"https://www.youtube.com/embed/{video_id}", "YouTube"
    
    # TikTok
    if "tiktok.com" in url:
        # استخراج معرف الفيديو من رابط المشاركة
        tiktok_match = re.search(r"tiktok\.com/(?:@[\w.-]+/video/|v/|embed/)(\d+)", url)
        if tiktok_match:
            video_id = tiktok_match.group(1)
            # استخدام رابط التضمين الرسمي
            return f"https://www.tiktok.com/embed/v2/{video_id}", "TikTok"
        
        # إذا كان الرابط مباشراً (مثل الرابط الذي وفرته)
        if "bytedance.map.fastly.net" in url:
            # نستخدم خدمة خارجية لتضمين TikTok
            encoded_url = quote(url, safe='')
            return f"https://www.tiktok.com/embed?url={encoded_url}", "TikTok"
        
        return url, "TikTok"
    
    # Instagram
    if "instagram.com" in url:
        post_match = re.search(r"instagram\.com/(?:p|reels)/([^/?]+)", url)
        if post_match:
            post_id = post_match.group(1)
            return f"https://www.instagram.com/p/{post_id}/embed/captioned/", "Instagram"
        return url, "Instagram"
    
    # Twitter/X
    if "twitter.com" in url or "x.com" in url:
        tweet_match = re.search(r"(?:twitter\.com|x\.com)/(?:\w+)/status/(\d+)", url)
        if tweet_match:
            tweet_id = tweet_match.group(1)
            return f"https://twitframe.com/show?url=https://twitter.com/i/status/{tweet_id}", "Twitter/X"
        return url, "Twitter/X"
    
    # الروابط العامة
    if url.endswith(('.mp4', '.webm', '.mov', '.ogg')):
        return url, "فيديو مباشر"
    
    return url, "رابط خارجي"

# --- الراوتات ---
@app.route("/", methods=["GET", "POST"])
def index():
    current_year = datetime.now().year
    
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        url = request.form.get("url", "").strip()
        
        if not name or not url:
            flash("الرجاء إدخال الاسم والرابط", "error")
            return redirect(url_for("index"))
        
        embed_url, platform = make_embed(url)
        
        if insert_video(name, url, platform, embed_url):
            flash("تم إرسال الرابط بنجاح ✅", "success")
        else:
            flash("هذا الرابط موجود مسبقاً في النظام", "warning")
        
        return redirect(url_for("index"))
    
    return render_template("index.html", now=datetime.now(), current_year=current_year)

@app.route("/admin", methods=["GET"])
def admin():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    
    return render_template("admin.html", now=datetime.now())

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    current_year = datetime.now().year
    
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin"))
        else:
            flash("كلمة المرور غير صحيحة ❌", "error")
    
    return render_template("login.html", current_year=current_year)

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("تم تسجيل الخروج بنجاح", "info")
    return redirect(url_for("admin_login"))

# --- واجهات برمجية للوحة الإدارة ---
@app.route("/api/videos")
def api_videos():
    if not session.get("admin"):
        return jsonify({"error": "غير مصرح"}), 401
    
    videos = get_videos()
    video_list = []
    for video in videos:
        video_list.append({
            "id": video["id"],
            "name": video["name"],
            "platform": video["platform"],
            "embed_url": video["embed_url"],
            "created_at": video["created_at"]
        })
    return jsonify(video_list)

@app.route("/api/videos/<int:video_id>")
def api_video(video_id):
    if not session.get("admin"):
        return jsonify({"error": "غير مصرح"}), 401
    
    video = get_video_by_id(video_id)
    if video:
        return jsonify({
            "id": video["id"],
            "name": video["name"],
            "platform": video["platform"],
            "embed_url": video["embed_url"]
        })
    return jsonify({"error": "الفيديو غير موجود"}), 404

@app.route("/api/videos/clear", methods=["POST"])
def api_clear_videos():
    if not session.get("admin"):
        return jsonify({"error": "غير مصرح"}), 401
    
    delete_all_videos()
    return jsonify({"success": True, "message": "تم حذف جميع الفيديوهات"})

@app.route("/api/videos/<int:video_id>/delete", methods=["DELETE"])
def api_delete_video(video_id):
    if not session.get("admin"):
        return jsonify({"error": "غير مصرح"}), 401
    
    delete_video(video_id)
    return jsonify({"success": True, "message": "تم حذف الفيديو"})

if __name__ == "__main__":
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)