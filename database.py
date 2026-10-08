import os
import sqlite3
from datetime import datetime, timezone

DATA_DIR = os.getenv('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'sakura18.db')

def now():
    return datetime.now(timezone.utc).isoformat()

class Database:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.init()

    def connect(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        return c

    def init(self):
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS users(
              telegram_id INTEGER PRIMARY KEY,
              username TEXT, first_name TEXT, last_name TEXT,
              language TEXT DEFAULT 'ru', balance REAL NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS actions(
              id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL,
              action_type TEXT NOT NULL, details TEXT, created_at TEXT NOT NULL,
              FOREIGN KEY(telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS messages(
              id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL,
              telegram_message_id INTEGER, direction TEXT NOT NULL, content_type TEXT,
              text TEXT, created_at TEXT NOT NULL,
              FOREIGN KEY(telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS categories(
              id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
              description TEXT DEFAULT '', sort_order INTEGER NOT NULL DEFAULT 0,
              active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS products(
              id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER NOT NULL,
              name TEXT NOT NULL, description TEXT DEFAULT '', price REAL NOT NULL DEFAULT 0,
              delivery_type TEXT NOT NULL DEFAULT 'file', delivery_value TEXT DEFAULT '',
              active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE RESTRICT
            );
            CREATE TABLE IF NOT EXISTS purchases(
              id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL,
              product_id INTEGER NOT NULL, price REAL NOT NULL, created_at TEXT NOT NULL,
              FOREIGN KEY(telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
              FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE RESTRICT
            );
            CREATE TABLE IF NOT EXISTS payments(
              id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL,
              charge_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL,
              amount REAL NOT NULL, currency TEXT NOT NULL, created_at TEXT NOT NULL,
              FOREIGN KEY(telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_actions_user ON actions(telegram_id,id DESC);
            CREATE INDEX IF NOT EXISTS idx_products_cat ON products(category_id,active,id);
            CREATE INDEX IF NOT EXISTS idx_purchases_user ON purchases(telegram_id,id DESC);
            ''')
            # Migrate the old database if an old balance column is absent.
            cols = {r[1] for r in c.execute('PRAGMA table_info(users)').fetchall()}
            if 'balance' not in cols:
                c.execute('ALTER TABLE users ADD COLUMN balance REAL NOT NULL DEFAULT 0')
            c.commit()
            self.seed()

    def seed(self):
        samples = [
            ('🕵️ Онлайн-квесты', 'Расследования, тайны и интерактивные дела.', 1),
            ('🎲 НРИ', 'Материалы для настольных ролевых игр.', 2),
            ('🎨 Творчество', 'Шаблоны, ассеты, карты и наборы для хобби.', 3),
            ('🎮 Игры и DLC', 'Легальные цифровые ключи и игровые дополнения.', 4),
            ('🧩 Пазлы и головоломки', 'Цифровые головоломки, загадки и мини-игры.', 5),
        ]
        with self.connect() as c:
            for name, desc, order in samples:
                c.execute('INSERT OR IGNORE INTO categories(name,description,sort_order,created_at) VALUES(?,?,?,?)',
                          (name, desc, order, now()))
            # Add demo cards only when catalog is empty. Delivery values are intentionally empty placeholders.
            count = c.execute('SELECT COUNT(*) FROM products').fetchone()[0]
            if count == 0:
                cats = {r['name']: r['id'] for r in c.execute('SELECT id,name FROM categories').fetchall()}
                demos = [
                    (cats['🕵️ Онлайн-квесты'], 'Дело №01: Последний звонок', 'Онлайн-расследование: сайт-квест с уликами, персонажами и подсказками. После покупки выдается ссылка на ваш GitHub Pages/хостинг.', 299, 'link'),
                    (cats['🕵️ Онлайн-квесты'], 'Дело №02: Тайна квартиры 407', 'Интерактивный детектив с поиском улик и логикой расследования. Ссылка на сайт после покупки.', 349, 'link'),
                    (cats['🕵️ Онлайн-квесты'], 'Дело №03: Исчезновение куратора', 'Короткий онлайн-квест на 30–60 минут для компании друзей.', 249, 'link'),
                    (cats['🎲 НРИ'], 'Генератор персонажа для D&D 5e', 'Веб-генератор персонажа. Можно разместить на GitHub Pages и выдавать ссылку после покупки.', 199, 'link'),
                    (cats['🎲 НРИ'], 'Ведьмак — Том Хаоса', 'Цифровой материал для НРИ. Загружайте только файл, права на распространение которого у вас есть.', 499, 'file'),
                    (cats['🎲 НРИ'], '100 ваншотов для НРИ', 'Сборник идей и готовых сценариев для игровых вечеров.', 299, 'file'),
                    (cats['🎨 Творчество'], 'Набор карт для виртуальных настолок', 'Пак из карт/ассетов для Foundry, Roll20 или другого VTT.', 249, 'file'),
                    (cats['🎨 Творчество'], 'Генератор имён и сюжетных зацепок', 'Небольшой веб-инструмент для мастеров и авторов.', 149, 'link'),
                    (cats['🎮 Игры и DLC'], 'Легальный игровой ключ', 'Карточка товара под официальный цифровой ключ. Ключ добавляется администратором.', 999, 'file'),
                    (cats['🧩 Пазлы и головоломки'], 'Набор цифровых детективных загадок', 'PDF/архив с головоломками для компании или вечеринки.', 199, 'file'),
                ]
                for cat, name, desc, price, dtype in demos:
                    c.execute('''INSERT INTO products(category_id,name,description,price,delivery_type,delivery_value,active,created_at,updated_at)
                                 VALUES(?,?,?,?,?,'',0,?,?)''', (cat,name,desc,price,dtype,now(),now()))
            c.commit()

    def get_user(self, uid):
        with self.connect() as c: return c.execute('SELECT * FROM users WHERE telegram_id=?',(uid,)).fetchone()
    def users(self):
        with self.connect() as c: return c.execute('SELECT * FROM users ORDER BY last_seen_at DESC').fetchall()
    def upsert_user(self, uid, username, first, last, language=None):
        with self.connect() as c:
            old=c.execute('SELECT telegram_id FROM users WHERE telegram_id=?',(uid,)).fetchone()
            if old:
                c.execute('UPDATE users SET username=?,first_name=?,last_name=?,language=COALESCE(?,language),last_seen_at=? WHERE telegram_id=?',(username,first,last,language,now(),uid))
            else:
                c.execute('INSERT INTO users(telegram_id,username,first_name,last_name,language,balance,created_at,last_seen_at) VALUES(?,?,?,?,?,0,?,?)',(uid,username,first,last,language or 'ru',now(),now()))
            c.commit()
    def touch_user(self,uid):
        with self.connect() as c: c.execute('UPDATE users SET last_seen_at=? WHERE telegram_id=?',(now(),uid)); c.commit()
    def add_action(self,uid,typ,details=''):
        with self.connect() as c: c.execute('INSERT INTO actions(telegram_id,action_type,details,created_at) VALUES(?,?,?,?)',(uid,typ,details or '',now())); c.commit()
    def actions(self,uid,limit=500):
        with self.connect() as c: return c.execute('SELECT * FROM actions WHERE telegram_id=? ORDER BY id DESC LIMIT ?',(uid,limit)).fetchall()
    def add_message(self,uid,mid,direction,ctype,text=''):
        with self.connect() as c: c.execute('INSERT INTO messages(telegram_id,telegram_message_id,direction,content_type,text,created_at) VALUES(?,?,?,?,?,?)',(uid,mid,direction,ctype,text or '',now())); c.commit()
    def messages(self,uid,limit=500):
        with self.connect() as c: return c.execute('SELECT * FROM messages WHERE telegram_id=? ORDER BY id DESC LIMIT ?',(uid,limit)).fetchall()
    def categories(self,active_only=False):
        with self.connect() as c: return c.execute('SELECT * FROM categories '+('WHERE active=1 ' if active_only else '')+'ORDER BY sort_order,id').fetchall()
    def get_category(self,cid):
        with self.connect() as c: return c.execute('SELECT * FROM categories WHERE id=?',(cid,)).fetchone()
    def add_category(self,name,description=''):
        with self.connect() as c:
            cur=c.execute('INSERT INTO categories(name,description,sort_order,created_at) VALUES(?,?,?,?)',(name,description,999,now())); c.commit(); return cur.lastrowid
    def update_category(self,cid,name,description):
        with self.connect() as c: c.execute('UPDATE categories SET name=?,description=? WHERE id=?',(name,description,cid)); c.commit()
    def toggle_category(self,cid):
        with self.connect() as c: c.execute('UPDATE categories SET active=1-active WHERE id=?',(cid,)); c.commit()
    def products(self,category_id=None,active_only=False):
        q='SELECT p.*,c.name category_name FROM products p JOIN categories c ON c.id=p.category_id WHERE 1=1'
        args=[]
        if category_id is not None: q+=' AND p.category_id=?'; args.append(category_id)
        if active_only: q+=' AND p.active=1 AND c.active=1'
        q+=' ORDER BY p.id DESC'
        with self.connect() as c: return c.execute(q,args).fetchall()
    def get_product(self,pid):
        with self.connect() as c: return c.execute('SELECT p.*,c.name category_name FROM products p JOIN categories c ON c.id=p.category_id WHERE p.id=?',(pid,)).fetchone()
    def add_product(self,category_id,name,description,price,dtype,value=''):
        with self.connect() as c:
            cur=c.execute('INSERT INTO products(category_id,name,description,price,delivery_type,delivery_value,active,created_at,updated_at) VALUES(?,?,?,?,?,?,1,?,?)',(category_id,name,description,price,dtype,value,now(),now())); c.commit(); return cur.lastrowid
    def update_product(self,pid,**fields):
        allowed={'category_id','name','description','price','delivery_type','delivery_value','active'}
        sets=[]; args=[]
        for k,v in fields.items():
            if k in allowed: sets.append(f'{k}=?'); args.append(v)
        if not sets:return
        sets.append('updated_at=?'); args.append(now()); args.append(pid)
        with self.connect() as c: c.execute(f'UPDATE products SET {", ".join(sets)} WHERE id=?',args); c.commit()
    def toggle_product(self,pid):
        with self.connect() as c: c.execute('UPDATE products SET active=1-active,updated_at=? WHERE id=?',(now(),pid)); c.commit()
    def change_balance(self,uid,delta):
        with self.connect() as c:
            c.execute('UPDATE users SET balance=MAX(0,balance+?),last_seen_at=? WHERE telegram_id=?',(delta,now(),uid)); c.commit()
            return c.execute('SELECT balance FROM users WHERE telegram_id=?',(uid,)).fetchone()['balance']
    def set_balance(self,uid,value):
        with self.connect() as c: c.execute('UPDATE users SET balance=MAX(0,?),last_seen_at=? WHERE telegram_id=?',(value,now(),uid)); c.commit()
    def purchase(self,uid,pid):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            u=c.execute('SELECT balance FROM users WHERE telegram_id=?',(uid,)).fetchone()
            p=c.execute('SELECT * FROM products WHERE id=? AND active=1',(pid,)).fetchone()
            if not u or not p: return None,'Товар недоступен.'
            if float(u['balance'])+1e-9 < float(p['price']): return None,'Недостаточно средств.'
            c.execute('UPDATE users SET balance=balance-?,last_seen_at=? WHERE telegram_id=?',(p['price'],now(),uid))
            cur=c.execute('INSERT INTO purchases(telegram_id,product_id,price,created_at) VALUES(?,?,?,?)',(uid,pid,p['price'],now()))
            c.execute('INSERT INTO actions(telegram_id,action_type,details,created_at) VALUES(?,?,?,?)',(uid,'purchase',f"#{pid} {p['name']} за {p['price']:.2f} ₽",now()))
            c.commit()
            return (dict(p),cur.lastrowid),'OK'
    def record_payment(self,uid,charge_id,payload,amount,currency):
        with self.connect() as c:
            try:
                c.execute('INSERT INTO payments(telegram_id,charge_id,payload,amount,currency,created_at) VALUES(?,?,?,?,?,?)',(uid,charge_id,payload,amount,currency,now())); c.commit(); return True
            except sqlite3.IntegrityError:return False
    def stats(self):
        with self.connect() as c:
            return {'users':c.execute('SELECT COUNT(*) FROM users').fetchone()[0], 'products':c.execute('SELECT COUNT(*) FROM products').fetchone()[0], 'active_products':c.execute('SELECT COUNT(*) FROM products WHERE active=1').fetchone()[0], 'categories':c.execute('SELECT COUNT(*) FROM categories WHERE active=1').fetchone()[0], 'purchases':c.execute('SELECT COUNT(*) FROM purchases').fetchone()[0], 'revenue':c.execute('SELECT COALESCE(SUM(price),0) FROM purchases').fetchone()[0], 'balance':c.execute('SELECT COALESCE(SUM(balance),0) FROM users').fetchone()[0]}
