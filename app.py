from flask import Flask, render_template, request, redirect, url_for, flash, session
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
import asyncio
import os
import threading

app = Flask(__name__)
app.secret_key = os.urandom(24)

# تخزين المستخدمين (في الذاكرة)
active_users = {}
user_lock = threading.Lock()

def run_async(coro):
    """تشغيل كود async في Flask"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login_step1():
    try:
        api_id = request.form['api_id']
        api_hash = request.form['api_hash']
        phone = request.form['phone']

        # إنشاء عميل تيليجرام
        client = TelegramClient('session', int(api_id), api_hash)
        
        # حفظ البيانات في الجلسة
        session_id = phone.replace('+', '').replace(' ', '')
        
        with user_lock:
            active_users[session_id] = {
                'client': client,
                'phone': phone,
                'api_id': api_id,
                'api_hash': api_hash,
                'status': 'waiting_code'
            }

        # بدء الاتصال وإرسال الكود
        try:
            run_async(client.connect())
            run_async(client.send_code_request(phone))
            flash('تم إرسال الكود إلى تيليجرام الخاص بك، يرجى إدخاله.', 'success')
            return redirect(url_for('verify_code', session_id=session_id))
        except Exception as e:
            flash(f'خطأ: {str(e)}', 'danger')
            return redirect(url_for('index'))
            
    except Exception as e:
        flash(f'خطأ: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/verify_code', methods=['GET', 'POST'])
def verify_code():
    session_id = request.args.get('session_id') or request.form.get('session_id')
    
    if request.method == 'POST':
        code = request.form['code']
        
        with user_lock:
            if session_id not in active_users:
                return redirect(url_for('index'))
                
            session_data = active_users[session_id]
            client = session_data['client']
            
            try:
                run_async(client.sign_in(phone=session_data['phone'], code=code))
                
                if client.is_user_authorized():
                    # الحصول على معلومات المستخدم بشكل صحيح
                    me = run_async(client.get_me())
                    user_id = me.id if me else None
                    
                    session_data['status'] = 'logged_in'
                    session_data['user_id'] = user_id
                    flash('تم تسجيل الدخول بنجاح!', 'success')
                    return redirect(url_for('dashboard', session_id=session_id))
                else:
                    session_data['status'] = 'waiting_2fa'
                    flash('يوجد تحقق بخطوتين، يرجى إدخال كلمة المرور.', 'warning')
                    return redirect(url_for('verify_2fa', session_id=session_id))
                    
            except SessionPasswordNeededError:
                session_data['status'] = 'waiting_2fa'
                flash('يوجد تحقق بخطوتين، يرجى إدخال كلمة المرور.', 'warning')
                return redirect(url_for('verify_2fa', session_id=session_id))
                
            except PhoneCodeInvalidError:
                flash('الكود غير صحيح، حاول مرة أخرى.', 'danger')
                return render_template('index.html', step='code', session_id=session_id)
                
    return render_template('index.html', step='code', session_id=session_id)

@app.route('/verify_2fa', methods=['GET', 'POST'])
def verify_2fa():
    session_id = request.args.get('session_id') or request.form.get('session_id')
    
    if request.method == 'POST':
        password = request.form['password']
        
        with user_lock:
            if session_id not in active_users:
                return redirect(url_for('index'))
                
            session_data = active_users[session_id]
            client = session_data['client']
            
            try:
                run_async(client.sign_in(password=password))
                
                # الحصول على معلومات المستخدم بشكل صحيح
                me = run_async(client.get_me())
                user_id = me.id if me else None
                
                session_data['status'] = 'logged_in'
                session_data['user_id'] = user_id
                flash('تم تسجيل الدخول بنجاح!', 'success')
                return redirect(url_for('dashboard', session_id=session_id))
            except Exception as e:
                flash(f'كلمة المرور خاطئة: {str(e)}', 'danger')
                return render_template('index.html', step='2fa', session_id=session_id)
                
    return render_template('index.html', step='2fa', session_id=session_id)

@app.route('/dashboard')
def dashboard():
    session_id = request.args.get('session_id')
    if session_id not in active_users or active_users[session_id]['status'] != 'logged_in':
        return redirect(url_for('index'))
    
    return render_template('index.html', step='dashboard', session_id=session_id)

@app.route('/send_message', methods=['POST'])
def send_message():
    session_id = request.form['session_id']
    group_id = request.form['group_id']
    message = request.form['message']
    
    with user_lock:
        if session_id not in active_users:
            return redirect(url_for('index'))
            
        client = active_users[session_id]['client']
        
        try:
            run_async(client.send_message(group_id, message))
            flash('تم إرسال الرسالة بنجاح!', 'success')
        except Exception as e:
            flash(f'فشل الإرسال: {str(e)}', 'danger')
            
    return redirect(url_for('dashboard', session_id=session_id))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
