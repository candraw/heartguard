from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
import pickle
import io
import pandas as pd
import re
import hashlib
from flask_mysqldb import MySQL
import MySQLdb.cursors
from flask import send_file
from fpdf import FPDF
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet


app = Flask(__name__)
app.secret_key = 'secret_key_bebas'

# Konfigurasi MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'db_flask'

# Inisialisasi MySQL
mysql = MySQL(app)

# Load model
with open('model.pkl', 'rb') as f:
    model = pickle.load(f)

# Daftar fitur sesuai urutan pelatihan
fitur = [
    'BMI', 'Smoking', 'AlcoholDrinking', 'Stroke', 'PhysicalHealth', 'MentalHealth',
    'DiffWalking', 'Sex', 'AgeCategory', 'Race', 'Diabetic', 'PhysicalActivity',
    'GenHealth', 'SleepTime', 'Asthma', 'KidneyDisease', 'SkinCancer'
]

THRESHOLD = 0.29

# ========================
# ROUTES LOGIN / REGISTER
# ========================

@app.route('/index', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):
            session['loggedin'] = True
            session['id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))
        else:
            msg = 'Username atau password salah!'
    return render_template('login.html', msg=msg)

@app.route('/register', methods=['GET', 'POST'])
@app.route('/register', methods=['GET', 'POST'])
@app.route('/register', methods=['GET', 'POST'])
def register():
    msg = ''
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        
        # Hash password sebelum simpan ke database
        hashed_password = generate_password_hash(password)

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        akun = cursor.fetchone()

        if akun:
            msg = 'Akun sudah terdaftar!'
        elif not re.match(r'^\w+$', username):
            msg = 'Username hanya boleh huruf dan angka!'
        else:
            cursor.execute('INSERT INTO users (email, username, password) VALUES (%s, %s, %s)', 
                           (email, username, hashed_password))
            mysql.connection.commit()
            msg = 'Pendaftaran berhasil! Silakan login.'
            return redirect(url_for('login'))
    return render_template('register.html', msg=msg)

@app.route('/edit_profil', methods=['GET', 'POST'])
def edit_profil():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM users WHERE id = %s', (session['id'],))
    user = cursor.fetchone()

    msg = ''
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']

        # Jika password diisi, hash dan update, jika tidak, hanya update email/username
        if password:
            from werkzeug.security import generate_password_hash
            hashed_pw = generate_password_hash(password)
            cursor.execute("""
                UPDATE users SET email = %s, username = %s, password = %s WHERE id = %s
            """, (email, username, hashed_pw, session['id']))
        else:
            cursor.execute("""
                UPDATE users SET email = %s, username = %s WHERE id = %s
            """, (email, username, session['id']))

        mysql.connection.commit()
        msg = 'Profil berhasil diperbarui!'
        session['username'] = username  # perbarui sesi juga

    return render_template('edit_profil.html', user=user, msg=msg)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ========================
# ROUTES UTAMA
# ========================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/profil')
def profil():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Ambil data akun user
    cursor.execute('SELECT * FROM users WHERE id = %s', (session['id'],))
    akun = cursor.fetchone()

    # Ambil riwayat prediksi user
    cursor.execute('SELECT * FROM prediction_history WHERE user_id = %s ORDER BY timestamp DESC', (session['id'],))
    riwayat = cursor.fetchall()

    return render_template('profil.html', akun=akun, riwayat=riwayat)


@app.route('/form')
def form():
    if 'loggedin' in session:
        return render_template('form.html')
    return redirect(url_for('login'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/predict', methods=['POST'])
def predict():
    try:
        if 'loggedin' not in session:
            return redirect(url_for('login'))

        data_input = {f: request.form[f] for f in fitur}
        
        # Konversi tipe data
        for kolom in ['BMI', 'PhysicalHealth', 'MentalHealth', 'SleepTime']:
            data_input[kolom] = float(data_input[kolom])
        for kolom in set(fitur) - {'BMI', 'PhysicalHealth', 'MentalHealth', 'SleepTime'}:
            data_input[kolom] = int(data_input[kolom])
        
        df = pd.DataFrame([data_input])
        proba = model.predict_proba(df)[0][1]
        pred = 1 if proba >= THRESHOLD else 0
        hasil_prediksi = "Waspada, Anda Berisiko Penyakit Jantung" if pred == 1 else "Selamat, Anda Tidak Berisiko Penyakit Jantung"
        hasil_proba = round(proba, 3)

        # ===================
        # Tambahkan logika saran
        # ===================
        saran = []
        if data_input['BMI'] >= 25:
            saran.append("BMI Anda berada di atas normal. Pertimbangkan pola makan sehat dan olahraga rutin.")
        if data_input['Smoking'] == 1:
            saran.append("Kebiasaan merokok meningkatkan risiko penyakit jantung. Disarankan untuk berhenti merokok.")
        if data_input['AlcoholDrinking'] == 1:
            saran.append("Kurangi atau hindari konsumsi alkohol untuk menjaga kesehatan jantung.")
        if data_input['Stroke'] == 1:
            saran.append("Riwayat stroke dapat meningkatkan risiko penyakit jantung. Periksa kondisi Anda secara berkala.")
        if data_input['SleepTime'] < 6:
            saran.append("Jam tidur kurang dari 6 jam. Usahakan tidur cukup untuk menjaga kesehatan jantung.")
        if data_input['PhysicalActivity'] == 0:
            saran.append("Kurangnya aktivitas fisik dapat meningkatkan risiko penyakit jantung. Lakukan olahraga ringan secara rutin.")
        if data_input['GenHealth'] in [0, 1]:  # 0: Poor, 1: Fair (misal mapping seperti itu)
            saran.append("Kesehatan umum Anda tergolong kurang baik. Jaga pola makan, tidur, dan olahraga.")
        if data_input['DiffWalking'] == 1:
            saran.append("Kesulitan berjalan bisa jadi tanda masalah kesehatan serius. Periksakan ke dokter.")

        # Simpan ke database
        cursor = mysql.connection.cursor()
        cursor.execute("""INSERT INTO prediction_history (
            user_id, BMI, Smoking, AlcoholDrinking, Stroke, PhysicalHealth,
            MentalHealth, DiffWalking, Sex, AgeCategory, Race, Diabetic,
            PhysicalActivity, GenHealth, SleepTime, Asthma, KidneyDisease,
            SkinCancer, prediction_result, probability
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            session['id'],
            data_input['BMI'],
            data_input['Smoking'],
            data_input['AlcoholDrinking'],
            data_input['Stroke'],
            data_input['PhysicalHealth'],
            data_input['MentalHealth'],
            data_input['DiffWalking'],
            data_input['Sex'],
            data_input['AgeCategory'],
            data_input['Race'],
            data_input['Diabetic'],
            data_input['PhysicalActivity'],
            data_input['GenHealth'],
            data_input['SleepTime'],
            data_input['Asthma'],
            data_input['KidneyDisease'],
            data_input['SkinCancer'],
            hasil_prediksi,
            hasil_proba
        ))
        mysql.connection.commit()

        return render_template('result.html', hasil_prediksi=hasil_prediksi, hasil_proba=f"{hasil_proba:.3f}", saran=saran)

    except Exception as e:
        return render_template('result.html', hasil_prediksi="Terjadi kesalahan", hasil_proba=str(e))


@app.route('/riwayat/grafik')
def grafik():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT Sex, Smoking, prediction_result FROM prediction_history")
    records = cursor.fetchall()

    data = {
        'Male': {'Berisiko': 0, 'Tidak Berisiko': 0},
        'Female': {'Berisiko': 0, 'Tidak Berisiko': 0},
        'Smoking': {'Berisiko': 0, 'Tidak Berisiko': 0},
        'NonSmoking': {'Berisiko': 0, 'Tidak Berisiko': 0}
    }

    for row in records:
        # Gender
        gender = 'Male' if row['Sex'] == 1 else 'Female'

        # Prediction Result
        hasil = 'Berisiko' if row['prediction_result'].strip().startswith("Waspada") else 'Tidak Berisiko'

        # Update berdasarkan jenis kelamin
        data[gender][hasil] += 1

        # Update berdasarkan kebiasaan merokok
        if row['Smoking'] == 1:
            data['Smoking'][hasil] += 1
        else:
            data['NonSmoking'][hasil] += 1

    return render_template('grafik.html', data=data)

@app.route('/download/<int:id>')
def download_pdf(id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("""
        SELECT ph.*, u.username FROM prediction_history ph 
        JOIN users u ON ph.user_id = u.id 
        WHERE ph.id = %s AND ph.user_id = %s
    """, (id, session['id']))
    data = cursor.fetchone()

    if not data:
        return "Data tidak ditemukan atau Anda tidak memiliki akses.", 404

    def label_value(field, value):
        mapping = {
            "Smoking": {0: "Tidak", 1: "Ya"},
            "AlcoholDrinking": {0: "Tidak", 1: "Ya"},
            "Stroke": {0: "Tidak", 1: "Ya"},
            "DiffWalking": {0: "Tidak", 1: "Ya"},
            "PhysicalActivity": {0: "Tidak", 1: "Ya"},
            "Asthma": {0: "Tidak", 1: "Ya"},
            "KidneyDisease": {0: "Tidak", 1: "Ya"},
            "SkinCancer": {0: "Tidak", 1: "Ya"},
            "Sex": {0: "Perempuan", 1: "Laki-laki"},
            "AgeCategory": {
                0: "18–24 Tahun", 1: "25–29 Tahun", 2: "30–34 Tahun", 3: "35–39 Tahun",
                4: "40–44 Tahun", 5: "45–49 Tahun", 6: "50–54 Tahun", 7: "55–59 Tahun",
                8: "60–64 Tahun", 9: "65–69 Tahun", 10: "70–74 Tahun", 11: "75–79 Tahun", 12: "80+ Tahun"
            },
            "Race": {
                0: "American Indian / Alaskan Native", 1: "Asian", 2: "Black",
                3: "Hispanic", 4: "Other", 5: "White"
            },
            "Diabetic": {
                0: "Tidak", 1: "Borderline Diabetes", 2: "Ya", 3: "Ya (Kehamilan)"
            },
            "GenHealth": {
                4: "Sangat Baik", 1: "Kurang Baik Baik", 2: "Cukup Baik",
                0: "Tidak Baik", 3: "Baik"
            }
        }
        return mapping.get(field, {}).get(value, value)

    # Data untuk tabel
    data_tabel = [
        ['Username', data['username']],
        ['BMI', data['BMI']],
        ['Merokok', label_value('Smoking', data['Smoking'])],
        ['Konsumsi Alkohol', label_value('AlcoholDrinking', data['AlcoholDrinking'])],
        ['Riwayat Stroke', label_value('Stroke', data['Stroke'])],
        ['Hari Fisik Tidak Sehat', data['PhysicalHealth']],
        ['Hari Mental Tidak Sehat', data['MentalHealth']],
        ['Kesulitan Berjalan', label_value('DiffWalking', data['DiffWalking'])],
        ['Jenis Kelamin', label_value('Sex', data['Sex'])],
        ['Kategori Usia', label_value('AgeCategory', data['AgeCategory'])],
        ['Ras', label_value('Race', data['Race'])],
        ['Status Diabetes', label_value('Diabetic', data['Diabetic'])],
        ['Aktivitas Fisik', label_value('PhysicalActivity', data['PhysicalActivity'])],
        ['Kesehatan Umum', label_value('GenHealth', data['GenHealth'])],
        ['Jam Tidur', data['SleepTime']],
        ['Asma', label_value('Asthma', data['Asthma'])],
        ['Penyakit Ginjal', label_value('KidneyDisease', data['KidneyDisease'])],
        ['Kanker Kulit', label_value('SkinCancer', data['SkinCancer'])],
        # ['Probabilitas', f"{data['probability']:.3f}"],
        ['Hasil Prediksi', data['prediction_result']]
        
    ]

    # PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=30)
    styles = getSampleStyleSheet()
    style_title = styles['Title']
    style_title.alignment = 1  # center

    elemen = []
    elemen.append(Paragraph("🫀 Laporan Prediksi Risiko Penyakit Jantung", style_title))
    elemen.append(Spacer(1, 12))

    table = Table(data_tabel, colWidths=[160, 320], hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#005792')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
        ('BOX', (0, 0), (-1, -1), 1, colors.grey),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    elemen.append(table)
    elemen.append(Spacer(1, 5))
    # Generate saran otomatis berdasarkan data
    saran = []
    if data['BMI'] >= 25:
        saran.append("BMI Anda berada di atas normal. Pertimbangkan pola makan sehat dan olahraga rutin.")
    if data['Smoking'] == 1:
        saran.append("Kebiasaan merokok meningkatkan risiko penyakit jantung. Disarankan untuk berhenti merokok.")
    if data['AlcoholDrinking'] == 1:
        saran.append("Kurangi atau hindari konsumsi alkohol untuk menjaga kesehatan jantung.")
    if data['Stroke'] == 1:
        saran.append("Riwayat stroke dapat meningkatkan risiko penyakit jantung. Periksa kondisi Anda secara berkala.")
    if data['SleepTime'] < 6:
        saran.append("Jam tidur kurang dari 6 jam. Usahakan tidur cukup untuk menjaga kesehatan jantung.")
    if data['PhysicalActivity'] == 0:
        saran.append("Kurangnya aktivitas fisik dapat meningkatkan risiko penyakit jantung. Lakukan olahraga ringan secara rutin.")
    if data['GenHealth'] in [0, 1]:  # Misal 0: Poor, 1: Fair
        saran.append("Kesehatan umum Anda tergolong kurang baik. Jaga pola makan, tidur, dan olahraga.")
    if data['DiffWalking'] == 1:
        saran.append("Kesulitan berjalan bisa jadi tanda masalah kesehatan serius. Periksakan ke dokter.")

    # Tambahkan heading "Saran Kesehatan"
    if saran:
        elemen.append(Spacer(1, 10))
        elemen.append(Paragraph("<b>Saran :</b>", styles['Heading3']))
        for poin in saran:
            elemen.append(Paragraph(f"• {poin}", styles['Normal']))
    
    elemen.append(Spacer(1, 10))
    # Opsional: Tambahkan catatan atau tips
    tips = Paragraph(
        "<b>Catatan:</b> Hasil prediksi ini hanya bersifat indikatif dan tidak menggantikan diagnosis medis. "
        "Konsultasikan dengan tenaga kesehatan profesional untuk pemeriksaan lebih lanjut.",
        styles['Normal']
    )
    elemen.append(tips)

    doc.build(elemen)
    buffer.seek(0)

    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=laporan_prediksi_{id}.pdf'

    return response

@app.route('/detail/<int:id>')
def detail_prediction(id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("""
        SELECT ph.*, u.username FROM prediction_history ph 
        JOIN users u ON ph.user_id = u.id 
        WHERE ph.id = %s AND ph.user_id = %s
    """, (id, session['id']))
    data = cursor.fetchone()

    if not data:
        return "Data tidak ditemukan atau Anda tidak memiliki akses.", 404

    def label_value(field, value):
        mapping = {
            "Smoking": {0: "Tidak", 1: "Ya"},
            "AlcoholDrinking": {0: "Tidak", 1: "Ya"},
            "Stroke": {0: "Tidak", 1: "Ya"},
            "DiffWalking": {0: "Tidak", 1: "Ya"},
            "PhysicalActivity": {0: "Tidak", 1: "Ya"},
            "Asthma": {0: "Tidak", 1: "Ya"},
            "KidneyDisease": {0: "Tidak", 1: "Ya"},
            "SkinCancer": {0: "Tidak", 1: "Ya"},
            "Sex": {0: "Perempuan", 1: "Laki-laki"},
            "AgeCategory": {
                0: "18–24 Tahun", 1: "25–29 Tahun", 2: "30–34 Tahun", 3: "35–39 Tahun",
                4: "40–44 Tahun", 5: "45–49 Tahun", 6: "50–54 Tahun", 7: "55–59 Tahun",
                8: "60–64 Tahun", 9: "65–69 Tahun", 10: "70–74 Tahun", 11: "75–79 Tahun", 12: "80+ Tahun"
            },
            "Race": {
                0: "American Indian / Alaskan Native", 1: "Asian", 2: "Black",
                3: "Hispanic", 4: "Other", 5: "White"
            },
            "Diabetic": {
                0: "Tidak", 1: "Borderline Diabetes", 2: "Ya", 3: "Ya (Kehamilan)"
            },
            "GenHealth": {
                4: "Sangat Baik", 1: "Kurang Baik Baik", 2: "Cukup Baik",
                0: "Tidak Baik", 3: "Baik"
            }
        }
        return mapping.get(field, {}).get(value, value)

    # Buat list saran
    saran = []
    if data['BMI'] >= 25:
        saran.append("BMI Anda berada di atas normal. Pertimbangkan pola makan sehat dan olahraga rutin.")
    if data['Smoking'] == 1:
        saran.append("Kebiasaan merokok meningkatkan risiko penyakit jantung. Disarankan untuk berhenti merokok.")
    if data['AlcoholDrinking'] == 1:
        saran.append("Kurangi atau hindari konsumsi alkohol untuk menjaga kesehatan jantung.")
    if data['Stroke'] == 1:
        saran.append("Riwayat stroke dapat meningkatkan risiko penyakit jantung. Periksa kondisi Anda secara berkala.")
    if data['SleepTime'] < 6:
        saran.append("Jam tidur kurang dari 6 jam. Usahakan tidur cukup untuk menjaga kesehatan jantung.")
    if data['PhysicalActivity'] == 0:
        saran.append("Kurangnya aktivitas fisik dapat meningkatkan risiko penyakit jantung. Lakukan olahraga ringan secara rutin.")
    if data['GenHealth'] in [0, 1]:
        saran.append("Kesehatan umum Anda tergolong kurang baik. Jaga pola makan, tidur, dan olahraga.")
    if data['DiffWalking'] == 1:
        saran.append("Kesulitan berjalan bisa jadi tanda masalah kesehatan serius. Periksakan ke dokter.")

    return render_template('detail.html', data=data, label_value=label_value, saran=saran)


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0')
