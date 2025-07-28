import os
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, session, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text


load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "fallback-secret")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

last_role_ar = {
    'admin': 'الرئيس المباشر',
    'hr': 'مدير الموارد البشرية',
    'entry': 'مدخل الترشيحات'
}

db = SQLAlchemy(app)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(255), nullable=False)
    national_id = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    phone_number = db.Column(db.String(20))
    job_number = db.Column(db.String(50), unique=True)
    qualification = db.Column(db.String(100))
    specialization = db.Column(db.String(100))
    role = db.Column(db.String(50), nullable=False)  
    password_hash = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TrainingCourse(db.Model):
    __tablename__ = 'training_courses'
    id = db.Column(db.Integer, primary_key=True)
    course_title = db.Column(db.String(255), nullable=False)
    region = db.Column(db.String(100))
    delivery_mode = db.Column(db.String(50))  
    start_date = db.Column(db.Date)
    duration_days = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class Nomination(db.Model):
    __tablename__ = 'nominations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('training_courses.id'), nullable=False)
    status = db.Column(db.String(50), default='pending')
    submission_date = db.Column(db.DateTime, default=datetime.utcnow)
    final_status = db.Column(db.String(50), default='draft')
    rejection_reason = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)

    user = db.relationship('User', backref='nominations') 
    course = db.relationship('TrainingCourse', backref='nominations')

    approval_logs = db.relationship('ApprovalLog', backref='nomination', lazy=True, cascade="all, delete-orphan")

class ApprovalLog(db.Model):
    __tablename__ = 'approval_logs'
    id = db.Column(db.Integer, primary_key=True)
    nomination_id = db.Column(db.Integer, db.ForeignKey('nominations.id'), nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    role = db.Column(db.String(50))   
    status = db.Column(db.String(50)) 
    notes = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

    approver = db.relationship('User', foreign_keys=[approved_by])

@app.route('/')
def home():
    featured_courses = TrainingCourse.query \
        .order_by(TrainingCourse.start_date) \
        .limit(3) \
        .all()

    return render_template('home.html',
                           featured_courses=featured_courses)

from werkzeug.security import check_password_hash

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        job_number = request.form['job_number']
        password = request.form['password']
        
        user = User.query.filter_by(job_number=job_number).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['user_role'] = user.role
            return redirect(url_for('dashboard')) 
            
        else:
            return render_template('login.html', error="بيانات الدخول غير صحيحة.")
    
    return render_template('login.html')
from sqlalchemy.orm import joinedload

@app.route('/dashboard')
def dashboard():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    user = User.query.get(user_id)

    if user.role == 'admin':
        filter_status = request.args.get('filter_status')

        nominations = Nomination.query \
            .filter_by(status='pending') \
            .order_by(Nomination.submission_date.desc()) \
            .all()
        unread_nominations = Nomination.query \
            .filter_by(status='pending', is_read=False) \
            .all()

        previous_logs = ApprovalLog.query \
            .join(Nomination) \
            .filter(
                ApprovalLog.role == 'admin',
                Nomination.status.in_(['approved', 'rejected'])
            ) \
            .order_by(ApprovalLog.timestamp.desc()) \
            .all()

        return render_template(
            'dashboard_admin.html',
            user=user,
            nominations=nominations,
            new_requests_count=len(unread_nominations),
            unread_nominations=unread_nominations,
            previous_logs=previous_logs,
            filter_status=filter_status
        )

    elif user.role == 'hr':
        filter_status = request.args.get('filter_status')

        nominations = Nomination.query \
            .filter_by(status='approved', final_status='draft') \
            .all()
        unread_nominations = Nomination.query \
            .filter_by(status='approved', final_status='draft', is_read=False) \
            .all()

        previous_logs = ApprovalLog.query \
            .join(Nomination) \
            .filter(
                ApprovalLog.role == 'hr',
                Nomination.status.in_(['approved', 'rejected'])
            ) \
            .order_by(ApprovalLog.timestamp.desc()) \
            .all()

        last_role_ar = {
            'admin': 'الرئيس المباشر',
            'hr': 'مدير الموارد البشرية',
            'entry': 'مدخل الترشيحات'
        }

        return render_template(
            'dashboard_hr_manager.html',
            user=user,
            nominations=nominations,
            new_requests_count=len(unread_nominations),
            unread_nominations=unread_nominations,
            previous_logs=previous_logs,
            filter_status=filter_status,
            last_role_ar=last_role_ar
        )

    elif user.role == 'manager':
        delivery_mode_filter = request.args.get('delivery_mode')
        region_filter = request.args.get('region')

        courses_query = TrainingCourse.query
        if delivery_mode_filter:
            courses_query = courses_query.filter_by(delivery_mode=delivery_mode_filter)
        if region_filter:
            courses_query = courses_query.filter_by(region=region_filter)

        courses = courses_query.order_by(TrainingCourse.start_date).all()

        return render_template(
            'dashboard_manager.html',
            user=user,
            courses=courses
        )

    elif user.role == 'entry':
        filter_status = request.args.get('filter_status')

        nominations = Nomination.query \
            .filter_by(status='approved', final_status='approved') \
            .all()
        unread_nominations = Nomination.query \
            .filter_by(status='approved', final_status='approved', is_read=False) \
            .all()

        previous_logs = ApprovalLog.query \
            .join(Nomination) \
            .filter(ApprovalLog.role == 'entry') \
            .order_by(ApprovalLog.timestamp.desc()) \
            .all()

        return render_template(
            'dashboard_entry.html',
            user=user,
            nominations=nominations,
            unread_nominations=unread_nominations,
            new_requests_count=len(unread_nominations),
            previous_logs=previous_logs,
            filter_status=filter_status
        )

    else:
        delivery_mode_filter = request.args.get('delivery_mode')
        region_filter = request.args.get('region')
        status_filter = request.args.get('filter_status')
        course_filter = request.args.get('filter_course')

        courses_query = TrainingCourse.query
        if delivery_mode_filter:
            courses_query = courses_query.filter_by(delivery_mode=delivery_mode_filter)
        if region_filter:
            courses_query = courses_query.filter_by(region=region_filter)
        courses = courses_query.order_by(TrainingCourse.start_date).all()

        nominations_query = Nomination.query.filter_by(user_id=user_id)
        if status_filter:
            nominations_query = nominations_query.filter_by(status=status_filter)
        if course_filter:
            nominations_query = nominations_query.filter_by(course_id=course_filter)
        nominations = nominations_query.order_by(Nomination.submission_date.desc()).all()

        submitted_courses = [n.course_id for n in nominations]
        user_nominations = nominations
        approval_logs_dict = {n.id: n.approval_logs for n in nominations}

        unread_logs = ApprovalLog.query \
            .join(Nomination) \
            .options(
                joinedload(ApprovalLog.nomination)
                .joinedload(Nomination.course)
            ) \
            .filter(
                Nomination.user_id == user.id,
                ApprovalLog.is_read == False
            ) \
            .order_by(ApprovalLog.timestamp.desc()) \
            .all()

        new_requests_count = len(unread_logs)

        return render_template(
            'dashboard_employee.html',
            user=user,
            nominations=nominations,
            courses=courses,
            submitted_courses=submitted_courses,
            user_nominations=user_nominations,
            approval_logs_dict=approval_logs_dict,
            unread_logs=unread_logs,
            new_requests_count=new_requests_count
        )

from werkzeug.security import generate_password_hash

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        national_id = request.form['national_id']
        email = request.form['email']
        phone = request.form['phone']
        job_number = request.form['job_number']
        qualification = request.form['qualification']
        specialization = request.form['specialization']
        password = request.form['password']

        existing_user = User.query.filter(
            (User.job_number == job_number) |
            (User.email == email) |
            (User.national_id == national_id)
        ).first()
        if existing_user:
            return render_template('register.html', error="يوجد مستخدم مسجل بهذه البيانات.")

        hashed_password = generate_password_hash(password)

        new_user = User(
            full_name=full_name,
            national_id=national_id,
            email=email,
            phone_number=phone,
            job_number=job_number,
            qualification=qualification,
            specialization=specialization,
            role='employee',
            password_hash=hashed_password
        )

        try:
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            return render_template('register.html', error=f"حدث خطأ أثناء التسجيل: {str(e)}")

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/new_nomination', methods=['POST'])
def new_nomination():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    course_id = request.form['course_id']
    justification = request.form.get('justification', 'طلب ترشيح')

    user = User.query.get(user_id)
    print(" الموظف الذي يطلب الترشيح:", user.full_name)

    existing = Nomination.query.filter_by(user_id=user_id, course_id=course_id).first()
    if existing:
        return redirect_by_role(user.role)

    nomination = Nomination(
        user_id=user_id,
        course_id=course_id,
        status='pending',
        final_status='draft'
    )

    db.session.add(nomination)
    db.session.commit()

    return redirect_by_role(user.role)

def redirect_by_role(role):
    if role == 'employee':
        return redirect(url_for('dashboard'))
    elif role == 'manager':
        return redirect(url_for('dashboard'))
    elif role == 'admin':
        return redirect(url_for('dashboard'))
    elif role == 'hr':
        return redirect(url_for('dashboard'))
    elif role == 'entry':
        return redirect(url_for('dashboard'))
    else:
        return redirect(url_for('login'))

@app.route('/admin_panel')
def admin_panel():
    if 'user_role' not in session or session['user_role'] != 'admin':
        return redirect(url_for('login'))

    nominations = db.session.query(Nomination).join(TrainingCourse).join(User).all()
    new_requests_count = Nomination.query.filter_by(status='pending').count()

    return render_template('admin_panel.html',
                           nominations=nominations,
                           new_requests_count=new_requests_count)

@app.route('/dashboard')
def admin_dashboard():
    if session.get('user_role') != 'admin':
        return redirect(url_for('login'))

    filter_status = request.args.get('filter_status')

    if filter_status:
        nominations = Nomination.query.filter_by(status=filter_status).all()
    else:
        nominations = Nomination.query.all()

    unread_nominations = Nomination.query.filter_by(status='pending').all()
    new_requests_count = len(unread_nominations)

    user_id = session.get('user_id')
    user = User.query.get(user_id) if user_id else None

    return render_template(
        'dashboard_admin.html',
        nominations=nominations,
        new_requests_count=new_requests_count,
        unread_nominations=unread_nominations,
        filter_status=filter_status,
        user=user  
    )


@app.route('/admin_decide', methods=['POST'])
def admin_decide():
    if 'user_role' not in session or session['user_role'] not in ['admin', 'manager']:
        return redirect(url_for('login'))

    nomination_id = request.form.get('nomination_id')
    action = request.form.get('action')
    reason = request.form.get('rejection_reason')

    nomination = Nomination.query.get(nomination_id)
    user_id = session['user_id']
    role = session['user_role']

    if nomination:
        if action == 'approve':
            nomination.status = 'approved'
            nomination.final_status = 'draft'
            nomination.rejection_reason = None
            status = 'approved'
        elif action == 'reject':
            nomination.status = 'rejected'
            nomination.final_status = 'rejected'
            nomination.rejection_reason = reason or 'لم يتم ذكر السبب'
            status = 'rejected'

        log = ApprovalLog(
            nomination_id=nomination.id,
            approved_by=user_id,
            role=role,
            status=status,
            notes=reason if status == 'rejected' else 'تمت الموافقة من الرئيس المباشر'
        )

        db.session.add(log)
        db.session.commit()

    return redirect(url_for('admin_dashboard'))


@app.route('/messages')
def messages():
    if 'user_role' not in session or session['user_role'] != 'admin':
        return redirect(url_for('login'))

    nominations = Nomination.query.filter_by(status='pending', is_read=False).all()

    for n in nominations:
        n.is_read = True
    db.session.commit()

    return render_template('messages.html', nominations=nominations)

@app.route('/mark-as-read', methods=['POST'])
def mark_as_read():
    if 'user_role' not in session or session['user_role'] != 'admin':
        return redirect(url_for('login'))

    nomination_id = request.form.get('nomination_id')
    nomination = Nomination.query.get(nomination_id)

    if nomination:
        nomination.is_read = True
        db.session.commit()

    return redirect(url_for('dashboard'))

from sqlalchemy import or_
from math import ceil

@app.route('/dashboard-hr')
def dashboard_hr_manager():
    if session.get('user_role') != 'hr':
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    filter_status = request.args.get('filter_status', 'all')
    page = int(request.args.get('page', 1))
    per_page = 10

    base_query = Nomination.query.filter(
        Nomination.status == 'approved',
        Nomination.final_status == 'draft'
    ).order_by(Nomination.submission_date.desc())

    if filter_status == 'approved':
        base_query = base_query.filter(Nomination.final_status == 'approved')
    elif filter_status == 'rejected':
        base_query = base_query.filter(Nomination.final_status == 'rejected')

    nominations_paginated = base_query.paginate(page=page, per_page=per_page, error_out=False)

    unread_nominations = Nomination.query.filter_by(
        status='approved', final_status='draft', is_read=False
    ).all()

    return render_template(
        'dashboard_hr_manager.html',
        user=user,
        nominations=nominations_paginated.items,
        unread_nominations=unread_nominations,
        new_requests_count=len(unread_nominations),
        current_page=page,
        total_pages=nominations_paginated.pages,
        filter_status=filter_status
    )


@app.route('/hr_decide', methods=['POST'])
def hr_decide():
    if 'user_id' not in session or session.get('user_role') != 'hr':
        return redirect(url_for('login'))

    nomination_id = request.form['nomination_id']
    decision = request.form.get('decision')
    reason = request.form.get('rejection_reason')

    nomination = Nomination.query.get(nomination_id)
    user_id = session['user_id']
    role = session['user_role']

    if nomination:
        if decision == 'approve':
            nomination.status = 'approved'
            nomination.final_status = 'approved'  
            nomination.rejection_reason = None
            status = 'approved'
        elif decision == 'reject':
            nomination.status = 'rejected'
            nomination.final_status = 'rejected'
            nomination.rejection_reason = reason or 'لم يتم ذكر السبب'
            status = 'rejected'

        log = ApprovalLog(
            nomination_id=nomination.id,
            approved_by=user_id,
            role=role,
            status=status,
            notes=reason if status == 'rejected' else 'تمت الموافقة من الموارد البشرية'
        )

        db.session.add(log)
        db.session.commit()

    return redirect(url_for('dashboard_hr_manager'))


@app.route('/update_user', methods=['POST'])
def update_user():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    full_name = request.form.get('full_name')
    phone_number = request.form.get('phone_number')

    user.full_name = full_name
    user.phone_number = phone_number

    db.session.commit()

    return redirect(url_for('dashboard'))

@app.route('/dashboard_entry')
def dashboard_entry():
    if session.get('user_role') != 'entry':
        return redirect(url_for('login'))

    user_id = session.get('user_id')
    user = User.query.get(user_id)

    filter_status = request.args.get('filter_status', 'all')

    if filter_status == 'approved':
        nominations = Nomination.query.filter_by(final_status='approved').all()
    elif filter_status == 'submitted':
        nominations = Nomination.query.filter_by(final_status='submitted').all()
    else:
        
        nominations = Nomination.query.filter(Nomination.final_status.in_(['approved', 'submitted'])).all()

    new_requests_count = len(nominations)

    return render_template(
        'dashboard_entry.html',
        user=user,
        nominations=nominations,
        filter_status=filter_status,
        new_requests_count=new_requests_count
    )

@app.route('/entry_decide', methods=['POST'])
def entry_decide():
    if session.get('user_role') != 'entry':
        return redirect(url_for('login'))

    nomination_id = request.form.get('nomination_id')
    nomination = Nomination.query.get(nomination_id)
    user_id = session.get('user_id')

    if nomination:
        nomination.final_status = 'submitted'
        nomination.status = 'approved'
        nomination.rejection_reason = None

        log = ApprovalLog(
            nomination_id=nomination.id,
            approved_by=user_id,
            role='entry',
            status='submitted',
            notes='تم الاعتماد النهائي ورفع الترشيح إلى معهد الإدارة',
            timestamp=datetime.utcnow()
        )

        db.session.add(log)
        db.session.commit()

    return redirect(url_for('dashboard_entry'))


@app.route('/entry_submit', methods=['POST'])
def entry_submit():
    nomination_id = request.form.get('nomination_id')
    nomination = Nomination.query.get(nomination_id)

    if not nomination:
        flash('لم يتم العثور على الترشيح المطلوب.', 'danger')
        return redirect(url_for('dashboard'))

    nomination.final_status = 'submitted'

    log = ApprovalLog(
        nomination_id=nomination.id,
        approved_by=session.get('user_id'),
        role='entry',
        status='submitted',
        notes='تم رفع الترشيح إلى معهد الإدارة',
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    db.session.commit()

    flash('تم رفع الترشيح إلى معهد الإدارة.', 'success')
    return redirect(url_for('dashboard'))



@app.route('/entry_reject', methods=['POST'])
def entry_reject():
    nomination_id = request.form.get('nomination_id')
    reason = request.form.get('rejection_reason')

    nomination = Nomination.query.get(nomination_id)

    if nomination:
        nomination.final_status = 'rejected'
        nomination.status = 'rejected'
        nomination.rejection_reason = reason
        db.session.commit()

    return redirect(url_for('dashboard'))

@app.template_filter('translate_status')
def translate_status(status):
    return {
        'approved': 'تمت الموافقة',
        'rejected': 'تم الرفض',
        'submitted': 'تم الإرسال'
    }.get(status, status)

@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    if request.method == 'POST':
        course_title = request.form.get('course_title')
        region = request.form.get('region')
        delivery_mode = request.form.get('delivery_mode')
        start_date = request.form.get('start_date')
        duration_days = request.form.get('duration_days')

        from datetime import datetime
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')

        new_course = TrainingCourse(
            course_title=course_title,
            region=region,
            delivery_mode=delivery_mode,
            start_date=start_date,
            duration_days=int(duration_days)
        )
        db.session.add(new_course)
        db.session.commit()
        flash("تمت إضافة الدورة بنجاح!", "success")
        return redirect(url_for('dashboard_hr_manager'))  

    return render_template('add_course.html')

@app.route('/mark-log-as-read', methods=['POST'])
def mark_log_as_read():
    log_id = request.form.get('log_id')
    log = ApprovalLog.query.get(log_id)
    if log:
        log.is_read = True
        db.session.commit()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)