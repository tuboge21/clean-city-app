import os
import uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import boto3
from botocore.exceptions import NoCredentialsError
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-change-me')

# Database
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

class Base(DeclarativeBase):
    pass
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# Models
class Report(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    location: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(nullable=False)
    photo_url: Mapped[str] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

class Schedule(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[str] = mapped_column(nullable=False)
    location: Mapped[str] = mapped_column(nullable=False)
    time: Mapped[str] = mapped_column(nullable=False)

class Officer(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    area: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(default='Active')

# S3 config
S3_BUCKET = os.environ.get('S3_BUCKET')
S3_REGION = os.environ.get('AWS_REGION', 'ap-southeast-2')
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name=S3_REGION
)

def upload_file_to_s3(file, bucket, folder='reports'):
    if not file or file.filename == '':
        return None
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    new_filename = f"{uuid.uuid4().hex}.{ext}"
    key = f"{folder}/{new_filename}"
    try:
        s3_client.upload_fileobj(file, bucket, key, ExtraArgs={'ACL': 'public-read'})
        url = f"https://{bucket}.s3.{S3_REGION}.amazonaws.com/{key}"
        return url
    except NoCredentialsError:
        return None

# Routes publik
@app.route('/')
def index():
    reports = Report.query.order_by(Report.created_at.desc()).limit(10).all()
    return render_template('index.html', reports=reports)

@app.route('/report', methods=['GET', 'POST'])
def report():
    if request.method == 'POST':
        location = request.form['location']
        description = request.form['description']
        photo = request.files.get('photo')
        photo_url = upload_file_to_s3(photo, S3_BUCKET) if photo else None
        new_report = Report(location=location, description=description, photo_url=photo_url)
        db.session.add(new_report)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('report.html')

@app.route('/schedule')
def schedule():
    schedules = Schedule.query.all()
    return render_template('schedule.html', schedules=schedules)

@app.route('/officers')
def officers():
    officers_list = Officer.query.all()
    return render_template('officers.html', officers=officers_list)

# Admin routes
ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('ADMIN_PASS', 'admin123')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['username'] == ADMIN_USER and request.form['password'] == ADMIN_PASS:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error='Invalid credentials')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    reports = Report.query.order_by(Report.created_at.desc()).all()
    schedules = Schedule.query.all()
    officers = Officer.query.all()
    return render_template('admin_dashboard.html', reports=reports, schedules=schedules, officers=officers)

@app.route('/admin/schedules', methods=['GET', 'POST'])
def admin_schedules():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        day = request.form['day']
        location = request.form['location']
        time = request.form['time']
        new_schedule = Schedule(day=day, location=location, time=time)
        db.session.add(new_schedule)
        db.session.commit()
        return redirect(url_for('admin_schedules'))
    schedules = Schedule.query.all()
    return render_template('admin_schedules.html', schedules=schedules)

@app.route('/admin/schedules/delete/<int:id>')
def delete_schedule(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    sched = Schedule.query.get_or_404(id)
    db.session.delete(sched)
    db.session.commit()
    return redirect(url_for('admin_schedules'))

@app.route('/admin/officers', methods=['GET', 'POST'])
def admin_officers():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        name = request.form['name']
        area = request.form['area']
        status = request.form['status']
        new_officer = Officer(name=name, area=area, status=status)
        db.session.add(new_officer)
        db.session.commit()
        return redirect(url_for('admin_officers'))
    officers = Officer.query.all()
    return render_template('admin_officers.html', officers=officers)

@app.route('/admin/officers/delete/<int:id>')
def delete_officer(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    off = Officer.query.get_or_404(id)
    db.session.delete(off)
    db.session.commit()
    return redirect(url_for('admin_officers'))

# Create tables dan sample data
with app.app_context():
    db.create_all()
    if Schedule.query.count() == 0:
        sample = [
            Schedule(day='Senin', location='Kelurahan Meruya', time='08:00-10:00'),
            Schedule(day='Rabu', location='Kelurahan Kembangan', time='09:00-11:00'),
            Schedule(day='Jumat', location='Kelurahan Duri Kepa', time='07:00-09:00')
        ]
        db.session.add_all(sample)
        db.session.commit()
    if Officer.query.count() == 0:
        sample_off = [
            Officer(name='Budi Santoso', area='Kelurahan Meruya', status='Active'),
            Officer(name='Siti Aminah', area='Kelurahan Kembangan', status='Active')
        ]
        db.session.add_all(sample_off)
        db.session.commit()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)