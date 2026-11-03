from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import mysql.connector
from mysql.connector import pooling
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from llama_cpp import Llama

ph = PasswordHasher()

REPO_ID = "bartowski/Qwen2.5-0.5B-Instruct-GGUF"
FILENAME = "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"

print(f"Загрузка модели {FILENAME} из {REPO_ID}...")
llm = Llama.from_pretrained(
    repo_id=REPO_ID,
    filename=FILENAME,
    n_ctx=2048,
    verbose=False
)
print("Модель успешно загружена.")

app = Flask(__name__)
app.secret_key = "1581"

db_config = {
    "host": "185.114.247.43",
    "port": 3306,
    "database": "sch688_vvedenie",
    "user": "sch688_vvedenie",
    "password": "Qwerty123"
}
db_pool = pooling.MySQLConnectionPool(pool_name="mypool", pool_size=5, **db_config)


@app.route("/")
def registration():
    return render_template('registration.html')


@app.route("/login")
def login_page():
    return render_template('login.html')


@app.route("/welcome")
def welcome():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('welcome.html')


@app.route('/profile')
def profile_page():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    try:
        cnx = db_pool.get_connection()
        cur = cnx.cursor(dictionary=True)
        cur.execute(
            'SELECT id, username, email, balance FROM users WHERE id = %s',
            (session['user_id'],)
        )
        user = cur.fetchone()
    finally:
        if 'cur' in locals(): cur.close()
        if 'cnx' in locals(): cnx.close()

    if not user:
        session.clear()
        return redirect(url_for('login_page'))

    return render_template('profile.html', user=user)


@app.route('/transactions')
def transactions_page():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    try:
        cnx = db_pool.get_connection()
        cur = cnx.cursor(dictionary=True)
        cur.execute(
            '''SELECT id, amount, type, cost, description, balance_after, created_at
               FROM transactions
               WHERE user_id = %s
               ORDER BY created_at DESC, id DESC''',
            (session['user_id'],)
        )
        transactions = cur.fetchall()
    finally:
        if 'cur' in locals(): cur.close()
        if 'cnx' in locals(): cnx.close()

    return render_template('transactions.html', transactions=transactions)


@app.route('/api/user_register', methods=['POST'])
def user_register():
    req = request.get_json() or {}
    name = req.get('name')
    email = req.get('email')
    password = req.get('password')

    if not name or not email or not password:
        return jsonify({'error': 'Переданы не все обязательные поля'}), 400

    password_hash = ph.hash(password)

    try:
        cnx = db_pool.get_connection()
        cur = cnx.cursor(dictionary=True)
        
        cur.execute('SELECT id FROM users WHERE email = %s', (email,))
        if cur.fetchone():
            return jsonify({'error': 'пользователь с таким email уже существует'}), 400

        cur.execute(
            'INSERT INTO `users`(`username`, `email`, `password_hash`) VALUES (%s, %s, %s)',
            (name, email, password_hash)
        )
        cnx.commit()
        return jsonify({'ok': True}), 201

    except mysql.connector.Error as err:
        return jsonify({'error': f'Ошибка базы данных: {err}'}), 500
    finally:
        if 'cur' in locals(): cur.close()
        if 'cnx' in locals(): cnx.close()


@app.route('/api/login', methods=['POST'])
def user_login():
    req = request.get_json() or {}
    email = req.get('email')
    password = req.get('password')

    if not email or not password:
        return jsonify({'error': 'Введите email и пароль'}), 400

    try:
        cnx = db_pool.get_connection()
        cur = cnx.cursor(dictionary=True)
        cur.execute(
            'SELECT id, username, email, password_hash FROM users WHERE email = %s',
            (email,)
        )
        user = cur.fetchone()
    finally:
        if 'cur' in locals(): cur.close()
        if 'cnx' in locals(): cnx.close()

    if not user:
        return jsonify({'error': 'неверный email или пароль'}), 401

    try:
        ph.verify(user['password_hash'], password)
    except VerifyMismatchError:
        return jsonify({'error': 'неверный email или пароль'}), 401
    except Exception:
        return jsonify({'error': 'Ошибка при верификации данных аккаунта'}), 500

    session.clear()
    session['user_id'] = user['id']
    session['username'] = user['username']

    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'email': user['email']
    }), 200


@app.route('/api/chat', methods=['POST'])
def api_chat():
    if 'user_id' not in session:
        return jsonify({'error': 'не авторизован'}), 401
    
    req = request.get_json(silent=True) or {}
    message = (req.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'пустое сообщение'}), 400

    prompt = f"<|im_start|>system\nТы полезный ассистент. Отвечай кратко и по-русски.<|im_end|>\n<|im_start|>user\n{message}<|im_end|>\n<|im_start|>assistant\n"
    
    output = llm(
        prompt,
        max_tokens=150,
        temperature=0.7,
        stop=["<|im_end|>"]
    )
    reply = output['choices'][0]['text'].strip()
    return jsonify({'reply': reply})


@app.route('/logout', methods=['POST'])
def api_logout():
    session.clear()
    return redirect(url_for('login_page'))


if __name__ == '__main__':
    app.run(debug=True)