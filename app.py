from flask import Flask, render_template,flash, request, redirect, url_for, session
import pymysql.cursors 
from pymysql.cursors import DictCursor
from contextlib import contextmanager
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, date, timedelta

app = Flask(__name__)
app.secret_key = "StudyFlow_2025_secret_key"

# Veri tabanı bağlantı fonksiyonu 
DB_SETTINGS = {
    'host': 'localhost',
    'user': "root",
    'password': '',
    'database': 'studyflow_db',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

@contextmanager 
def get_db_connection():
    """
    Veritabanı bağlantısını açar ve işi bitince otomatik olarak kapatır.
    """
    connection = None
    try:
        # DB_SETTINGS sözlüğündeki bilgilerle bağlantı kurar.
        connection = pymysql.connect(**DB_SETTINGS)
        # Bağlantıyı dışarıya verir (yield)
        yield connection
    except pymysql.Error as e:
        # Hata durumunda konsola yazdırır.
        print(f"Veritabanı bağlantı hatası: {e}")
        # Hata fırlatmayı sürdürür ki Flask hatayı yakalasın.
        raise
    finally:
        # İşlem başarılı olsa da hata olsa da bağlantıyı kapatır.
        if connection:
            connection.close()

# Gerekli Giriş Kontrolü Dekorasyonu
def login_required(f):
    """Bu fonksiyonu,sadece giriş yapmış kullanıcılıarın erişebileceği tüm Flask rotalarının üstüne ekleyeceğiz."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Eğer kullanıcının user_id'si session'da yoksa (yani giriş yapmamışsa)...
        if 'user_id' not in session:
            # Kullanıcıyı giriş sayfasına yönlendirir.
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Kayıt Fonksiyonu
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Form verilerini al
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        # Eğer bir alan bile boşsa, hata döndürür(Temel doğrulama)
        if not username or not email or not password:
            return "Lütfen tüm alanları doldurun.", 400
        
        # Şifreyi güvenli hale getir
        password_hash = generate_password_hash(password)

        # 2. Veritabanı işlemleri
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                # Güvenli SQL sorgusu 
                sql = "INSERT INTO users (username, email, password_hash) VALUES (%s,%s,%s)"
                print("--- SQL SORGUSU ÇALIŞTIRILIYOR ---")
                
                cursor.execute(sql, (username, email, password_hash))
                
                conn.commit()
                
                print("--- VERİTABANI BAŞARIYLA KAYDEDİLDİ ---")
            
            # Başarılı kayıt sonrası yönlendirme
            flash("Hesabınız başarıyla oluşturuldu! Lütfen giriş yapın.","success")
            return redirect(url_for('login'))
        
        
        except pymysql.err.IntegrityError as e:
            # Kullanıcı adı veya email zaten varsa (UNIQUE kısıtlaması ihlali)
            if e.args[0] == 1062:
                return "Bu kullanıcı adı veya e-posta adresi zaten kullanımda.", 409
            return f"Veritabanı bütünlük hatası oluştu: {e}", 500
        
        except pymysql.Error as e:
            # Diğer tüm MySQL/MariaDB hataları (Bağlantı kesilmesi, yetki sorunu vb.)
            return f"Veritabanı bağlantı veya sorgu hatası: {e}", 500
        
        except Exception as e:
            # Beklenmedik Python hataları
            return f"Beklenmedik bir hata oluştu: {e}", 500
            
    # GET isteği ise (formu gösterir)
    flash("Bu kullanıcı adı veya e-posta zaten kullanımda.","error")
    return render_template('register.html')
        
# Diğer Fonksiyonlar 
@app.route('/')
def index():
    # Uygulama Hakkında bilgi veren açılış sayfası
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = None
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                sql = "SELECT id, username, password_hash FROM users WHERE username = %s"
                cursor.execute(sql, (username,))
                user = cursor.fetchone()
        except pymysql.Error as e:
            return f"Veritabanı hatası: {e}", 500
            
        # Kullanıcı var mı ve şifre doğru mu?
        if user and check_password_hash(user['password_hash'], password):
            # Şifre doğruysa: Oturum (Session) başlat
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash("Giriş başarıyla tamamlandı. StudyFlow'a hoş geldiniz!","success")

            # Başarılı girişten sonra kullanıcıyı ana panele yönlendirir
            return redirect(url_for('dashboard'))
        else:
            return "Hata: Kullanıcı adı veya parola hatalı.", 401
            
    return render_template('login.html')

@app.route('/add_session', methods=['GET', 'POST'])
@login_required
def add_session():
    if request.method == 'POST':
        task_name = request.form.get('task_name')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        notes = request.form.get('notes')

        try:
            # Tarih ve saat nesnesine dönüştürme (üstte import ettik)
            start_time = datetime.fromisoformat(start_time_str)
            end_time = datetime.fromisoformat(end_time_str)
            
            # Süreyi hesaplama(dakika cinsinden)
            duration = end_time - start_time
            duration_minutes = int(duration.total_seconds() / 60)
        
        except ValueError:
            flash("Bitiş saati, başlangıç saatinden sonra olmalıdır.", "error")
            return "Hata: Geçersiz tarih/saat formatı.", 400
        
        # 2. Veritabanına kayıt
        user_id = session['user_id']
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                sql = """
                    INSERT INTO study_sessions
                    (user_id, task_name, start_time, end_time, duration_minutes, notes)
                    VALUES(%s, %s, %s, %s, %s, %s) 
                """
                cursor.execute(sql, (user_id, task_name, start_time, end_time, duration_minutes, notes))
                conn.commit()
            flash("Çalışma seansı başarıyla kaydedildi!","success")
            return redirect(url_for('dashboard'))
        except pymysql.Error as e:
            return f"Veritabanı hatası oluştu: {e}", 500
        
        except Exception as e:
            return f"Beklenmedik hata: {e}", 500
            
    return render_template('add_session.html')

@app.route('/logout')
def logout():
    # Oturumdaki bütün bilgileri siler
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required # sadece giriş yapanlar görebilir!
def dashboard():
    user_id = session['user_id']
    
    #  HTML'e gönderilecek veri listesi ve plan değişkenleri tanımlandı
    study_sessions_list = [] 
    current_plan = None 
    
    # --- Haftalık Başlangıç Hesaplama ---
    today = date.today()
    days_since_monday = today.weekday()
    week_start_date = today - timedelta(days=days_since_monday) # Bu haftanın Pazartesi'si
    next_monday = week_start_date + timedelta(weeks=1) 

    weekly_total_minutes = 0
    weekly_total_hours = 0
    weekly_remaining_minutes = 0

    try: 
        cursor_type = DictCursor
        with get_db_connection() as conn:
            cursor = conn.cursor(cursor_type) 
            
            # 1. HAFTALIK TOPLAM SÜREYİ ÇEKME
            sql_weekly_sum = """
                SELECT SUM(duration_minutes) AS total_minutes FROM study_sessions
                WHERE user_id = %s AND start_time >= %s
            """
            cursor.execute(sql_weekly_sum, (user_id, week_start_date))
            result = cursor.fetchone()
            
            # Haftalık toplam dakika hesaplaması (Düzeltildi)
            if result and result['total_minutes'] is not None:
                weekly_total_minutes = result['total_minutes']
                weekly_total_hours = weekly_total_minutes // 60
                weekly_remaining_minutes = weekly_total_minutes % 60
            
            # 2. AKTİF/GELECEK PLANLARI ÇEKME
            sql_current_plan = """
                SELECT * FROM weekly_plans 
                WHERE user_id = %s AND week_start_date >= %s
                ORDER BY week_start_date DESC LIMIT 1
            """
            cursor.execute(sql_current_plan, (user_id, week_start_date)) 
            current_plan = cursor.fetchone() 

            # 3. TÜM SEANSLARI ÇEKME
            sql_all = """
                SELECT id, task_name, start_time, end_time, duration_minutes, notes 
                FROM study_sessions 
                WHERE user_id = %s
                ORDER BY start_time DESC
            """
            cursor.execute(sql_all, (user_id,))
            study_sessions_list = cursor.fetchall()
                
    except pymysql.Error as e:
        flash(f"Veritabanı bağlantı hatası: {e}", "error")
        return redirect(url_for('login')) # Hata durumunda login sayfasına yönlendir

    # --- YENİ EKLENEN GRAFİK HESAPLAMALARI  ---
    
    # Haftalık hedefi belirle (15 saat = 900 dakika)
    DEFAULT_WEEKLY_GOAL_MINUTES = 15 * 60 

    # Toplam süreyi direkt veritabanından aldığımız weekly_total_minutes ile hesaplıyoruz
    if DEFAULT_WEEKLY_GOAL_MINUTES > 0:
        # İlerleme yüzdesi
        progress_percentage = min(100, round((weekly_total_minutes / DEFAULT_WEEKLY_GOAL_MINUTES) * 100))
    else:
        progress_percentage = 0
        
    # --- HTML'e tüm verileri tek bir return ile gönder ---
    return render_template('dashboard.html', 
        sessions=study_sessions_list, 
        weekly_total_minutes=weekly_total_minutes,
        weekly_total_hours=weekly_total_hours,
        weekly_remaining_minutes=weekly_remaining_minutes,
        week_start_date=week_start_date,
        current_plan=current_plan, 
        next_monday=next_monday,
        # YENİ GRAFİK VERİLERİ:
        progress_percentage=progress_percentage,
        default_goal_hours=DEFAULT_WEEKLY_GOAL_MINUTES / 60
    )

@app.route('/plan_week', methods=['GET', 'POST'])
@login_required 
def plan_week():
    # Haftalık plan, Pazartesi gününden başlar.
    today = date.today()
    days_since_monday = today.weekday()
    this_monday = today - timedelta(days=days_since_monday)
    next_monday = this_monday + timedelta(weeks=1)

    if request.method == 'POST':
        goals = request.form.get('goals')
        user_id = session['user_id']
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                sql = """
                    INSERT INTO weekly_plans 
                    (user_id, week_start_date, goals, is_completed) 
                    VALUES (%s, %s, %s, FALSE)
                """
                cursor.execute(sql, (user_id, next_monday, goals))
                conn.commit()
                
            return redirect(url_for('dashboard'))
            
        except pymysql.Error as e:
            return f"Veritabanı hatası oluştu: {e}", 500
        
        except Exception as e:
            return f"Beklenmedik hata: {e}", 500

    return render_template('plan_week.html', next_monday=next_monday)

@app.route('/edit_session/<int:session_id>', methods=["GET","POST"])
@login_required
def edit_session(session_id):
    # 1. Tüm DB işlemleri 'with' bloğu içinde 'conn' objesini kullanır.
    with get_db_connection() as conn:
        cursor = conn.cursor(DictCursor) # PyMySQL veya DictCursor'ı destekleyen bir kütüphane için
        
        cursor.execute(
            "SELECT * FROM study_sessions WHERE id = %s AND user_id = %s",
            (session_id, session['user_id'])
        )
        session_data = cursor.fetchone()

        if session_data is None:
            flash("Seans bulunamadı veya bu seansı düzenleme yetkiniz yok.","error")
            return redirect(url_for('dashboard'))
        
        if request.method == 'POST':
            try:
                task_name = request.form['task_name']
                start_time_str = request.form['start_time']
                end_time_str = request.form['end_time']
                notes = request.form.get('notes','')

                start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
                end_time = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M')

                # Süreyi tekrar hesapla
                duration = end_time - start_time
                duration_minutes = int(duration.total_seconds() / 60)

                if duration_minutes <= 0:
                    flash("Bitiş saati, başlangıç saatinden sonra olmalıdır.","error")
                    session_data.update(request.form)
                    return render_template('edit_session.html', study_session=session_data)
                
                sql ="""
                    UPDATE study_sessions
                    SET task_name = %s, start_time = %s, end_time = %s,
                        duration_minutes = %s, notes = %s
                    WHERE id = %s AND user_id = %s
                    """
                
                cursor.execute(sql, (
                    task_name, start_time, end_time, duration_minutes, notes,
                    session_id, session['user_id']
                ))
                
                conn.commit() 

                flash("Çalışma seansı başarıyla güncellendi!", "success")
                return redirect(url_for('dashboard'))
            
            except Exception as e:
                conn.rollback() 
                flash(f"Güncelleme sırasında bir hata oluştu: {e}", "error")
                session_data.update(request.form)
                return render_template('edit_session.html', study_session=session_data)
        
        # Formu göstermek için tarih formatlarını düzenle (GET isteği)
        session_data['start_time_formatted'] = session_data['start_time'].strftime('%Y-%m-%dT%H:%M')
        session_data['end_time_formatted'] = session_data['end_time'].strftime('%Y-%m-%dT%H:%M')

        return render_template('edit_session.html', study_session=session_data)

@app.route('/delete_session/<int:session_id>',methods=['POST'])
@login_required
def delete_session(session_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()

        sql = "DELETE FROM study_sessions WHERE id = %s AND user_id = %s"
        cursor.execute(sql , (session_id,session['user_id']))
        conn.commit()

        if cursor.rowcount > 0:
            flash("Çalışma seansı başarıyla silindi.","success")
        else:
            flash("Seans bulunamadı veya bu seansı silme yetkiniz yok.","error")

    return redirect(url_for('dashboard'))
# Uygulama Başlat
if __name__ == '__main__':
    app.run(debug=True)