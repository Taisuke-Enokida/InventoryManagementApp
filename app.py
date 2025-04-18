from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
from functools import wraps

# 管理者専用のデコレータを定義
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            return redirect(url_for('index'))  # 管理者でなければインデックスページにリダイレクト
        return f(*args, **kwargs)
    return decorated_function

app = Flask(__name__)
app.secret_key = 'your-secret-key'  # セッションに必要

DATABASE = 'inventory.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

    """データベースの初期化：テーブルを作成"""
def init_db():
    if not os.path.exists(DATABASE):  # データベースが存在しない場合のみ初期化
        conn = get_db_connection()
        cursor = conn.cursor()

        # 必要なテーブルを作成
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            unit TEXT NOT NULL,
            current_stock INTEGER NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        password TEXT NOT NULL,
        role TEXT CHECK(role IN ('admin', 'staff')) NOT NULL DEFAULT 'staff'
        );
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            type TEXT CHECK(type IN ('in', 'out')) NOT NULL,
            quantity INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            note TEXT,
            FOREIGN KEY (item_id) REFERENCES items(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        ''')

        conn.commit()
        conn.close()


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/inventory')
def inventory():
    conn = get_db_connection()
    items = conn.execute('''
        SELECT items.id, items.name, items.unit, items.current_stock, categories.name AS category_name
        FROM items
        LEFT JOIN categories ON items.category_id = categories.id
    ''').fetchall()
    conn.close()
    return render_template('inventory.html', items=items)

@app.route('/items/add', methods=['GET', 'POST'])
@admin_required
def add_item():
    conn = get_db_connection()

    if request.method == 'POST':
        name = request.form['name']
        category_id = request.form['category']
        unit = request.form['unit']
        current_stock = request.form['current_stock']

        # データベースに新しいアイテムを挿入
        conn.execute(
            'INSERT INTO items (name, category_id, unit, current_stock) VALUES (?, ?, ?, ?)',
            (name, category_id, unit, current_stock)
        )
        conn.commit()
        conn.close()
        
        # 登録後にリダイレクト（再度登録ページを表示）
        return redirect(url_for('add_item'))

    # GETメソッド：カテゴリー一覧を取得して表示
    categories = conn.execute('SELECT id, name FROM categories').fetchall()
    conn.close()
    return render_template('add_item.html', categories=categories)

@app.route('/categories/add', methods=['GET', 'POST'])
@admin_required
def add_category():
    if request.method == 'POST':
        name = request.form['name']

        # 新しいカテゴリーをデータベースに挿入
        conn = get_db_connection()
        conn.execute('INSERT INTO categories (name) VALUES (?)', (name,))
        conn.commit()
        conn.close()

        # カテゴリー登録後にリダイレクト（カテゴリー登録ページを再表示）
        return redirect(url_for('add_category'))

    return render_template('add_category.html')

@app.route('/edit/<int:item_id>', methods=['GET', 'POST'])
def edit_item(item_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    if request.method == 'POST':
        name = request.form['name']
        category_id = request.form['category_id']
        unit = request.form['unit']
        current_stock = request.form['current_stock']

        conn.execute('''
            UPDATE items
            SET name = ?, category_id = ?, unit = ?, current_stock = ?
            WHERE id = ?
        ''', (name, category_id, unit, current_stock, item_id))
        conn.commit()
        conn.close()
        return redirect(url_for('inventory'))

    # GET のときは item と categories を取得
    item = conn.execute('SELECT * FROM items WHERE id = ?', (item_id,)).fetchone()
    categories = conn.execute('SELECT * FROM categories').fetchall()
    conn.close()  # ← 全ての操作のあとで閉じる！

    return render_template('edit_item.html', item=item, categories=categories)

@app.route('/delete/<int:item_id>', methods=['POST'])
def delete_item(item_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM items WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('inventory'))

@app.route('/movement', methods=['GET', 'POST'])
def movement():
    conn = get_db_connection()
    items = conn.execute('SELECT * FROM items').fetchall()
    users = conn.execute('SELECT * FROM users').fetchall()

    if request.method == 'POST':
        item_id = int(request.form['item_id'])
        user_id = int(request.form['user_id'])
        move_type = request.form['type']
        quantity = int(request.form['quantity'])
        note = request.form.get('note', '')

        item = conn.execute('SELECT * FROM items WHERE id = ?', (item_id,)).fetchone()

        if move_type == 'in':
            new_stock = item['current_stock'] + quantity
        elif move_type == 'out':
            new_stock = item['current_stock'] - quantity
            if new_stock < 0:
                conn.close()
                return "在庫が不足しています", 400
        else:
            conn.close()
            return "不正な操作", 400

        # 更新処理
        conn.execute('UPDATE items SET current_stock = ? WHERE id = ?', (new_stock, item_id))
        conn.execute('''
            INSERT INTO stock_movements (item_id, user_id, type, quantity, note)
            VALUES (?, ?, ?, ?, ?)
        ''', (item_id, user_id, move_type, quantity, note))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))

    conn.close()
    return render_template('movement.html', items=items, users=users)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        password = request.form.get('password')
        role = request.form.get('role', 'staff')  # フォームに role を追加してもいい

        if not name or not password:
            return "名前とパスワードは必須です", 400

        conn = get_db_connection()
        conn.execute('INSERT INTO users (name, password, role) VALUES (?, ?, ?)', (name, password, role))
        conn.commit()
        conn.close()

        return redirect(url_for('index'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username and password:
            conn = get_db_connection()
            user = conn.execute(
                'SELECT * FROM users WHERE name = ?', (username,)
            ).fetchone()
            conn.close()

            if user and user['password'] == password:
                session['user_id'] = user['id']
                session['role'] = user['role']
                return redirect(url_for('index'))
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/movement/log')
def movement_log():
    conn = get_db_connection()
    logs = conn.execute('''
        SELECT sm.id, sm.type, sm.quantity, sm.timestamp, sm.note,
               i.name AS item_name, u.name AS user_name
        FROM stock_movements sm
        JOIN items i ON sm.item_id = i.id
        JOIN users u ON sm.user_id = u.id
        ORDER BY sm.timestamp DESC
    ''').fetchall()
    conn.close()
    return render_template('movement_log.html', logs=logs)

if __name__ == '__main__':
    # アプリが起動するたびにデータベースを初期化（最初の一回だけ）
    init_db()
    
    # Flask アプリケーションをデバッグモードで実行
    app.run(debug=True, port=5001)
