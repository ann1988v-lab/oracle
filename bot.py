import os, asyncio
from pathlib import Path
from datetime import datetime
from html import escape
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ButtonStyle
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, LabeledPrice, PreCheckoutQuery, SuccessfulPayment, Document
)
from database import Database
from locales import t

load_dotenv()
TOKEN=os.getenv('BOT_TOKEN','')
if not TOKEN: raise RuntimeError('BOT_TOKEN is not set in .env')

ADMIN_IDS={int(x.strip()) for x in os.getenv('ADMIN_IDS','8361114775,7628243006,8535032499,8666113991').split(',') if x.strip().isdigit()}
SUPPORT_URL=os.getenv('SUPPORT_URL','https://t.me/beIosheeev_kyc')
PAYMENT_PROVIDER_TOKEN=os.getenv('PAYMENT_PROVIDER_TOKEN','')
ADMIN_PAGE_SIZE=8

TOPUP_PACKAGES={300:300,500:500,1000:1000,2000:2000,5000:5000} # RUB -> kopecks

db=Database()
bot=Bot(TOKEN,default=DefaultBotProperties(parse_mode=ParseMode.HTML))
router=Router()
MEDIA=Path(__file__).resolve().parent/'media'
MEDIA.mkdir(exist_ok=True)
MAIN_IMAGE=MEDIA/'main.jpg'; CATALOG_IMAGE=MEDIA/'catalog.jpg'; PROFILE_IMAGE=MEDIA/'profile.jpg'; BALANCE_IMAGE=MEDIA/'balance.jpg'; ADMIN_IMAGE=MEDIA/'admin.jpg'; PRODUCT_IMAGE=MEDIA/'product.jpg'

class AddProduct(StatesGroup):
    name=State(); description=State(); price=State(); category=State(); category_name=State(); delivery_type=State(); delivery=State()
class EditProduct(StatesGroup):
    value=State()
class AddCategory(StatesGroup):
    name=State(); description=State()
class AdminBalance(StatesGroup):
    amount=State()

async def send_asset(message,image,text,reply_markup=None):
    if image.exists(): await message.answer_photo(FSInputFile(str(image)),caption=text,reply_markup=reply_markup)
    else: await message.answer(text,reply_markup=reply_markup)

def is_admin(uid): return uid in ADMIN_IDS

def main_kb(uid):
    rows=[
      [InlineKeyboardButton(text='🛍 Каталог',callback_data='catalog',style=ButtonStyle.SUCCESS)],
      [InlineKeyboardButton(text='👤 Профиль',callback_data='profile',style=ButtonStyle.PRIMARY),InlineKeyboardButton(text='💰 Баланс',callback_data='balance',style=ButtonStyle.SUCCESS)],
      [InlineKeyboardButton(text='💬 Поддержка',url=SUPPORT_URL,style=ButtonStyle.PRIMARY)]
    ]
    if is_admin(uid): rows.append([InlineKeyboardButton(text='🛠 Админ-панель',callback_data='adm:home')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def back_main(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🏠 Главное меню',callback_data='home')]])
def fmt_money(x): return f'{float(x):,.2f}'.replace(',',' ').replace('.',',')+' ₽'
def fmt_date(v):
    if not v:return '—'
    try:return datetime.fromisoformat(v.replace('Z','+00:00')).astimezone().strftime('%d.%m.%Y %H:%M')
    except:return str(v)[:19]

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text='🛍 Товары',callback_data='adm:products:0'),InlineKeyboardButton(text='➕ Добавить товар',callback_data='adm:addproduct')],
      [InlineKeyboardButton(text='📁 Категории',callback_data='adm:categories'),InlineKeyboardButton(text='➕ Категория',callback_data='adm:addcategory')],
      [InlineKeyboardButton(text='👥 Пользователи',callback_data='adm:users:0')],
      [InlineKeyboardButton(text='📊 Статистика',callback_data='adm:stats')],
      [InlineKeyboardButton(text='🏠 Магазин',callback_data='home')]
    ])

@router.message(CommandStart())
async def start(m:Message):
    old=db.get_user(m.from_user.id); db.upsert_user(m.from_user.id,m.from_user.username,m.from_user.first_name,m.from_user.last_name)
    db.add_message(m.from_user.id,m.message_id,'incoming','text','/start')
    db.add_action(m.from_user.id,'start','Повторный запуск' if old else 'Новый пользователь')
    await send_asset(m,MAIN_IMAGE,t('ru','welcome'),main_kb(m.from_user.id))

@router.callback_query(F.data=='home')
async def home(c:CallbackQuery,state:FSMContext):
    await state.clear(); db.touch_user(c.from_user.id)
    try: await c.message.delete()
    except: pass
    await send_asset(c.message,MAIN_IMAGE,t('ru','welcome'),main_kb(c.from_user.id)); await c.answer()

@router.callback_query(F.data=='catalog')
async def catalog(c:CallbackQuery):
    cats=db.categories(True)
    rows=[[InlineKeyboardButton(text=x['name'],callback_data=f'cat:{x["id"]}')] for x in cats]
    rows.append([InlineKeyboardButton(text='🏠 Главное меню',callback_data='home')])
    text='🛍 <b>КАТАЛОГ</b>\n\nВыбери направление — внутри будут доступные цифровые товары.\n\n🔮 После оплаты товар приходит сразу.'
    try: await c.message.delete()
    except: pass
    await send_asset(c.message,CATALOG_IMAGE,text,InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@router.callback_query(F.data.startswith('cat:'))
async def category(c:CallbackQuery):
    cid=int(c.data.split(':')[1]); cat=db.get_category(cid); products=db.products(cid,True)
    if not cat:return await c.answer('Категория не найдена',show_alert=True)
    rows=[]
    for p in products: rows.append([InlineKeyboardButton(text=f'🔹 {p["name"][:45]} — {fmt_money(p["price"])}',callback_data=f'product:{p["id"]}')])
    rows.append([InlineKeyboardButton(text='◀️ Категории',callback_data='catalog')])
    text=f'📁 <b>{escape(cat["name"])}</b>\n\n{escape(cat["description"] or "") or "Выбери товар:"}'
    if not products:text+='\n\nПока здесь ничего нет.'
    await c.message.edit_caption(caption=text,reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)) if c.message.photo else await c.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await c.answer()

@router.callback_query(F.data.startswith('product:'))
async def product(c:CallbackQuery):
    pid=int(c.data.split(':')[1]); p=db.get_product(pid)
    if not p or not p['active']:return await c.answer('Товар недоступен',show_alert=True)
    delivery='📦 Файл' if p['delivery_type']=='file' else '🔗 Ссылка'
    text=(f'🔮 <b>{escape(p["name"])}</b>\n\n'
          f'📁 {escape(p["category_name"])}\n{escape(p["description"] or "Описание не указано.")}\n\n'
          f'{delivery}\n💰 Цена: <b>{fmt_money(p["price"])}</b>')
    kb=InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text=f'💳 Купить за {fmt_money(p["price"])}',callback_data=f'buyproduct:{pid}',style=ButtonStyle.SUCCESS)],
      [InlineKeyboardButton(text='◀️ К категории',callback_data=f'cat:{p["category_id"]}')]
    ])
    await c.message.edit_caption(caption=text,reply_markup=kb) if c.message.photo else await c.message.edit_text(text,reply_markup=kb)
    await c.answer()

@router.callback_query(F.data.startswith('buyproduct:'))
async def buy_product(c:CallbackQuery):
    pid=int(c.data.split(':')[1]); result,status=db.purchase(c.from_user.id,pid)
    if not result:
        u=db.get_user(c.from_user.id)
        await c.answer(f'{status} Баланс: {fmt_money(u["balance"] if u else 0)}',show_alert=True); return
    p=result[0]; u=db.get_user(c.from_user.id); db.add_message(c.from_user.id,c.message.message_id,'outgoing','purchase',p['name'])
    await c.answer('Покупка оплачена!')
    await c.message.answer(f'✅ <b>Покупка оформлена!</b>\n\n{escape(p["name"])}\nСписано: <b>{fmt_money(p["price"])}</b>\nОстаток: <b>{fmt_money(u["balance"])}</b>')
    if p['delivery_type']=='link':
        if p['delivery_value']:
            await c.message.answer(f'🔗 <b>Ваша ссылка:</b>\n{escape(p["delivery_value"])}')
        else:
            await c.message.answer('⚠️ Товар куплен, но ссылка ещё не настроена. Обратитесь в поддержку.')
    else:
        if p['delivery_value']:
            try: await c.message.answer_document(p['delivery_value'],caption='📦 Ваш цифровой товар')
            except: await c.message.answer('⚠️ Товар куплен, но файл сейчас недоступен. Обратитесь в поддержку.')
        else:
            await c.message.answer('⚠️ Товар куплен, но файл ещё не загружен администратором. Обратитесь в поддержку.')

@router.callback_query(F.data=='profile')
async def profile(c:CallbackQuery):
    u=db.get_user(c.from_user.id)
    if not u:return await c.answer('Сначала /start',show_alert=True)
    text=(f'👤 <b>ПРОФИЛЬ</b>\n\n🆔 ID: <code>{u["telegram_id"]}</code>\n'
          f'👋 Username: {escape("@"+u["username"] if u["username"] else "—")}\n'
          f'💰 Баланс: <b>{fmt_money(u["balance"])}</b>\n📅 Регистрация: {fmt_date(u["created_at"])}')
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='💰 Пополнить баланс',callback_data='balance')],[InlineKeyboardButton(text='🛍 Каталог',callback_data='catalog')],[InlineKeyboardButton(text='🏠 Главное меню',callback_data='home')]])
    try: await c.message.delete()
    except: pass
    await send_asset(c.message,PROFILE_IMAGE,text,kb); await c.answer()

@router.callback_query(F.data=='balance')
async def balance(c:CallbackQuery):
    u=db.get_user(c.from_user.id); bal=fmt_money(u['balance'] if u else 0)
    rows=[[InlineKeyboardButton(text=f'💳 {amount} ₽',callback_data=f'topup:{amount}',style=ButtonStyle.SUCCESS)] for amount in TOPUP_PACKAGES]
    rows += [[InlineKeyboardButton(text='◀️ Профиль',callback_data='profile')],[InlineKeyboardButton(text='🏠 Главное меню',callback_data='home')]]
    text=f'💰 <b>БАЛАНС</b>\n\nСейчас: <b>{bal}</b>\n\nВыбери сумму пополнения. Оплата проходит через Telegram-платёж в рублях.'
    try: await c.message.delete()
    except: pass
    await send_asset(c.message,BALANCE_IMAGE,text,InlineKeyboardMarkup(inline_keyboard=rows)); await c.answer()

@router.callback_query(F.data.startswith('topup:'))
async def topup(c:CallbackQuery):
    amount=int(c.data.split(':')[1])
    if amount not in TOPUP_PACKAGES:return await c.answer('Сумма недоступна',show_alert=True)
    if not PAYMENT_PROVIDER_TOKEN:
        await c.answer('Не задан PAYMENT_PROVIDER_TOKEN. Добавь токен платёжного провайдера в переменные окружения.',show_alert=True); return
    payload=f'topup:{amount}'
    await c.message.answer_invoice(title=f'Пополнение на {amount} ₽',description=f'Пополнение баланса ORAKUL STORE на {amount} рублей.',payload=payload,provider_token=PAYMENT_PROVIDER_TOKEN,currency='RUB',prices=[LabeledPrice(label=f'{amount} ₽',amount=amount*100)])
    await c.answer()

@router.pre_checkout_query()
async def pre_checkout(q:PreCheckoutQuery):
    try: amount=int(q.invoice_payload.split(':')[1])
    except: return await q.answer(ok=False,error_message='Некорректный счёт.')
    if amount not in TOPUP_PACKAGES or q.currency!='RUB' or q.total_amount!=amount*100:
        return await q.answer(ok=False,error_message='Счёт устарел. Открой пополнение заново.')
    await q.answer(ok=True)

@router.message(F.successful_payment)
async def payment(m:Message):
    p=m.successful_payment
    try: amount=int(p.invoice_payload.split(':')[1])
    except: return await m.answer('⚠️ Не удалось определить платёж. Напиши в поддержку.')
    if amount not in TOPUP_PACKAGES or p.currency!='RUB' or p.total_amount!=amount*100:
        return await m.answer('⚠️ Платёж не прошёл проверку.')
    if not db.record_payment(m.from_user.id,p.telegram_payment_charge_id,p.invoice_payload,amount,p.currency):
        return await m.answer('Этот платёж уже был зачислен.')
    newbal=db.change_balance(m.from_user.id,amount); db.add_action(m.from_user.id,'balance_topup',f'+{amount} RUB')
    await m.answer(f'✅ <b>Баланс пополнен!</b>\n\nНачислено: <b>+{amount} ₽</b>\nТеперь на балансе: <b>{fmt_money(newbal)}</b>',reply_markup=main_kb(m.from_user.id))

@router.message(F.text=='/paysupport')
async def paysupport(m:Message): await m.answer(f'💬 Поддержка по оплате: {SUPPORT_URL}')

# ---------------- ADMIN ----------------
async def guard(c):
    if not is_admin(c.from_user.id): await c.answer('Нет доступа',show_alert=True); return False
    return True

@router.message(F.text=='/admin')
async def admin_command(m:Message):
    if is_admin(m.from_user.id): await send_asset(m,ADMIN_IMAGE,admin_text(),admin_kb())

def admin_text():
    s=db.stats(); return (f'🛠 <b>ORAKUL ADMIN</b>\n\n👥 Пользователи: <b>{s["users"]}</b>\n🛍 Товары: <b>{s["active_products"]}</b> активных / {s["products"]} всего\n📁 Категории: <b>{s["categories"]}</b>\n🧾 Покупки: <b>{s["purchases"]}</b>\n💰 Продажи: <b>{fmt_money(s["revenue"])}</b>\n💳 Балансы пользователей: <b>{fmt_money(s["balance"])}</b>')

@router.callback_query(F.data=='adm:home')
async def adm_home(c:CallbackQuery):
    if not await guard(c):return
    try: await c.message.delete()
    except: pass
    await send_asset(c.message,ADMIN_IMAGE,admin_text(),admin_kb()); await c.answer()

@router.callback_query(F.data.startswith('adm:products:'))
async def adm_products(c:CallbackQuery):
    if not await guard(c):return
    page=int(c.data.rsplit(':',1)[1]); items=db.products(); start=page*ADMIN_PAGE_SIZE; chunk=items[start:start+ADMIN_PAGE_SIZE]
    rows=[]
    for p in chunk: rows.append([InlineKeyboardButton(text=f'#{p["id"]} {p["name"][:35]} · {fmt_money(p["price"])}',callback_data=f'adm:product:{p["id"]}')])
    nav=[]
    if page:nav.append(InlineKeyboardButton(text='◀️',callback_data=f'adm:products:{page-1}'))
    if start+ADMIN_PAGE_SIZE<len(items):nav.append(InlineKeyboardButton(text='▶️',callback_data=f'adm:products:{page+1}'))
    if nav:rows.append(nav)
    rows.append([InlineKeyboardButton(text='➕ Добавить товар',callback_data='adm:addproduct')]);rows.append([InlineKeyboardButton(text='⬅️ Админка',callback_data='adm:home')])
    await c.message.edit_text(f'🛍 <b>ТОВАРЫ</b> · {len(items)}\n\nНажми на товар для редактирования:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows));await c.answer()

@router.callback_query(F.data.startswith('adm:product:'))
async def adm_product(c:CallbackQuery):
    if not await guard(c):return
    pid=int(c.data.split(':')[2]);p=db.get_product(pid)
    if not p:return await c.answer('Не найден',show_alert=True)
    status='🟢 Активен' if p['active'] else '🔴 Скрыт'; delivery='📦 Файл' if p['delivery_type']=='file' else '🔗 Ссылка'; ready='Да' if p['delivery_value'] else 'Нет'
    text=(f'🛍 <b>ТОВАР #{p["id"]}</b>\n\n<b>{escape(p["name"])}</b>\n📁 {escape(p["category_name"])}\n💰 {fmt_money(p["price"])}\n{status}\n{delivery} · заполнено: {ready}\n\n{escape(p["description"] or "—")}')
    kb=InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text='✏️ Название',callback_data=f'edit:name:{pid}'),InlineKeyboardButton(text='💰 Цена',callback_data=f'edit:price:{pid}')],
      [InlineKeyboardButton(text='📝 Описание',callback_data=f'edit:desc:{pid}'),InlineKeyboardButton(text='📁 Категория',callback_data=f'edit:cat:{pid}')],
      [InlineKeyboardButton(text='📦 Файл/ссылка',callback_data=f'edit:delivery:{pid}')],
      [InlineKeyboardButton(text='👁 Скрыть' if p['active'] else '👁 Опубликовать',callback_data=f'adm:toggleproduct:{pid}')],
      [InlineKeyboardButton(text='⬅️ Товары',callback_data='adm:products:0')]])
    await c.message.edit_text(text,reply_markup=kb);await c.answer()

@router.callback_query(F.data=='adm:addproduct')
async def add_product_start(c:CallbackQuery,state:FSMContext):
    if not await guard(c):return
    await state.clear();await state.set_state(AddProduct.name);await c.message.edit_text('➕ <b>Новый товар</b>\n\n1/7. Напиши название товара:');await c.answer()

@router.message(AddProduct.name)
async def add_name(m:Message,state:FSMContext): await state.update_data(name=(m.text or '').strip());await state.set_state(AddProduct.description);await m.answer('2/7. Напиши описание товара:')
@router.message(AddProduct.description)
async def add_desc(m:Message,state:FSMContext): await state.update_data(description=(m.text or '').strip());await state.set_state(AddProduct.price);await m.answer('3/7. Укажи цену в рублях, например <code>299</code> или <code>349.90</code>:')
@router.message(AddProduct.price)
async def add_price(m:Message,state:FSMContext):
    try:price=float((m.text or '').replace(',','.')); assert price>=0
    except: return await m.answer('Цена должна быть числом, например 299 или 349.90.')
    await state.update_data(price=price); await state.set_state(AddProduct.category)
    cats=db.categories(True);rows=[[InlineKeyboardButton(text=x['name'],callback_data=f'addcat:{x["id"]}')] for x in cats];rows.append([InlineKeyboardButton(text='➕ Создать категорию',callback_data='addcat:new')]);await m.answer('4/7. Выбери категорию:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data.startswith('addcat:'))
async def add_choose_cat(c:CallbackQuery,state:FSMContext):
    if not await guard(c):return
    x=c.data.split(':')[1]
    if x=='new': await state.set_state(AddProduct.category_name);await c.message.edit_text('Напиши название новой категории:');await c.answer();return
    await state.update_data(category_id=int(x));await state.set_state(AddProduct.delivery_type);await c.message.edit_text('5/7. Что будет выдаваться после покупки?',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📦 Telegram-файл',callback_data='adddelivery:file')],[InlineKeyboardButton(text='🔗 Ссылка',callback_data='adddelivery:link')]]));await c.answer()
@router.message(AddProduct.category_name)
async def add_cat_name(m:Message,state:FSMContext):
    name=(m.text or '').strip()
    try:cid=db.add_category(name)
    except: return await m.answer('Такая категория уже существует. Введи другое название.')
    await state.update_data(category_id=cid);await state.set_state(AddProduct.delivery_type);await m.answer('5/7. Выбери способ выдачи:',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📦 Telegram-файл',callback_data='adddelivery:file')],[InlineKeyboardButton(text='🔗 Ссылка',callback_data='adddelivery:link')]]))
@router.callback_query(F.data.startswith('adddelivery:'))
async def add_delivery_type(c:CallbackQuery,state:FSMContext):
    if not await guard(c):return
    dtype=c.data.split(':')[1];await state.update_data(delivery_type=dtype);await state.set_state(AddProduct.delivery)
    await c.message.edit_text('6/7. '+('Отправь сюда документ (PDF/ZIP/EPUB/DOCX и т.п.). Бот сохранит Telegram file_id.' if dtype=='file' else 'Отправь URL, например ссылку на GitHub Pages.'))
    await c.answer()
@router.message(AddProduct.delivery)
async def add_delivery(m:Message,state:FSMContext):
    data=await state.get_data();dtype=data['delivery_type']
    if dtype=='file':
        if not m.document:return await m.answer('Нужен именно документ Telegram (скрепка → Файл).')
        value=m.document.file_id
    else:
        value=(m.text or '').strip()
        if not value.startswith(('http://','https://')):return await m.answer('Нужна полноценная ссылка, начинающаяся с http:// или https://')
    data.update(delivery_value=value);pid=db.add_product(data['category_id'],data['name'],data['description'],data['price'],dtype,value);await state.clear();db.add_action(m.from_user.id,'admin_product_add',f'Товар #{pid}')
    await m.answer(f'✅ Товар <b>#{pid}</b> создан. Теперь его можно редактировать в разделе товаров.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✏️ Открыть товар',callback_data=f'adm:product:{pid}')],[InlineKeyboardButton(text='🛍 Товары',callback_data='adm:products:0')],[InlineKeyboardButton(text='🛠 Админка',callback_data='adm:home')]]))

@router.callback_query(F.data.startswith('edit:'))
async def edit_start(c:CallbackQuery,state:FSMContext):
    if not await guard(c):return
    _,field,pid=c.data.split(':');pid=int(pid);p=db.get_product(pid)
    if not p:return await c.answer('Товар не найден',show_alert=True)
    if field=='cat':
        rows=[[InlineKeyboardButton(text=x['name'],callback_data=f'editcat:{pid}:{x["id"]}')] for x in db.categories(True)];rows.append([InlineKeyboardButton(text='◀️ Назад',callback_data=f'adm:product:{pid}')]);await c.message.edit_text('Выбери новую категорию:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows));await c.answer();return
    if field=='delivery':
        rows=[[InlineKeyboardButton(text='📦 Новый файл',callback_data=f'editdtype:file:{pid}')],[InlineKeyboardButton(text='🔗 Новая ссылка',callback_data=f'editdtype:link:{pid}')],[InlineKeyboardButton(text='◀️ Назад',callback_data=f'adm:product:{pid}')]];await c.message.edit_text('Что хочешь заменить?',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows));await c.answer();return
    prompts={'name':'Новое название:','price':'Новая цена в рублях:','desc':'Новое описание:'}
    await state.set_state(EditProduct.value);await state.update_data(pid=pid,field=field);await c.message.edit_text(prompts[field]);await c.answer()
@router.message(EditProduct.value, F.text)
async def edit_value(m:Message,state:FSMContext):
    data=await state.get_data();pid=data['pid'];field=data['field'];value=(m.text or '').strip()
    if field=='delivery_link':
        if not value.startswith(('http://','https://')): return await m.answer('Нужна ссылка http:// или https://')
        db.update_product(pid,delivery_type='link',delivery_value=value); await state.clear(); return await m.answer('✅ Ссылка товара заменена.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='◀️ К товару',callback_data=f'adm:product:{pid}')]]))
    if field=='price':
        try:value=float(value.replace(',','.'));assert value>=0
        except:return await m.answer('Цена должна быть числом.')
    db.update_product(pid,**{ {'name':'name','price':'price','desc':'description'}[field]:value});await state.clear();await m.answer('✅ Изменение сохранено.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='◀️ К товару',callback_data=f'adm:product:{pid}')]]))
@router.callback_query(F.data.startswith('editcat:'))
async def edit_cat(c:CallbackQuery):
    if not await guard(c):return
    _,pid,cid=c.data.split(':');pid=int(pid);db.update_product(pid,category_id=int(cid));await c.answer('Категория изменена')
    p=db.get_product(pid)
    text=(f'🛍 <b>ТОВАР #{p["id"]}</b>\n\n<b>{escape(p["name"])}</b>\n📁 {escape(p["category_name"])}\n💰 {fmt_money(p["price"])}\n\n{escape(p["description"] or "—")}')
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✏️ Название',callback_data=f'edit:name:{pid}'),InlineKeyboardButton(text='💰 Цена',callback_data=f'edit:price:{pid}')],[InlineKeyboardButton(text='📝 Описание',callback_data=f'edit:desc:{pid}'),InlineKeyboardButton(text='📁 Категория',callback_data=f'edit:cat:{pid}')],[InlineKeyboardButton(text='📦 Файл/ссылка',callback_data=f'edit:delivery:{pid}')],[InlineKeyboardButton(text='⬅️ Товары',callback_data='adm:products:0')]])
    await c.message.edit_text(text,reply_markup=kb)

@router.callback_query(F.data.startswith('editdtype:'))
async def edit_dtype(c:CallbackQuery,state:FSMContext):
    if not await guard(c):return
    _,dtype,pid=c.data.split(':');await state.set_state(EditProduct.value);await state.update_data(pid=int(pid),field='delivery_'+dtype)
    await c.message.edit_text('Отправь новый документ:' if dtype=='file' else 'Отправь новый URL:');await c.answer()
@router.message(EditProduct.value,F.document)
async def edit_file(m:Message,state:FSMContext):
    d=await state.get_data()
    if d.get('field')!='delivery_file':return
    db.update_product(d['pid'],delivery_type='file',delivery_value=m.document.file_id);await state.clear();await m.answer('✅ Файл товара заменён.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='◀️ К товару',callback_data=f'adm:product:{d["pid"]}')]]))
@router.message(EditProduct.value)
async def edit_link_or_file_wrong(m:Message,state:FSMContext):
    d=await state.get_data()
    if d.get('field')=='delivery_link':
        value=(m.text or '').strip()
        if not value.startswith(('http://','https://')):return await m.answer('Нужна ссылка http:// или https://')
        db.update_product(d['pid'],delivery_type='link',delivery_value=value);await state.clear();await m.answer('✅ Ссылка товара заменена.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='◀️ К товару',callback_data=f'adm:product:{d["pid"]}')]]));return
    await m.answer('Нужен документ-файл.')

@router.callback_query(F.data.startswith('adm:toggleproduct:'))
async def toggle_product(c:CallbackQuery):
    if not await guard(c):return
    pid=int(c.data.split(':')[2]);db.toggle_product(pid);await c.answer('Статус изменён');await adm_product(c)

@router.callback_query(F.data=='adm:categories')
async def adm_categories(c:CallbackQuery):
    if not await guard(c):return
    rows=[]
    for x in db.categories(): rows.append([InlineKeyboardButton(text=f'{"🟢" if x["active"] else "🔴"} {x["name"]}',callback_data=f'adm:cat:{x["id"]}')])
    rows += [[InlineKeyboardButton(text='➕ Добавить категорию',callback_data='adm:addcategory')],[InlineKeyboardButton(text='⬅️ Админка',callback_data='adm:home')]]
    await c.message.edit_text('📁 <b>КАТЕГОРИИ</b>\n\nНажми на категорию для редактирования/скрытия.',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows));await c.answer()
@router.callback_query(F.data=='adm:addcategory')
async def add_category_start(c:CallbackQuery,state:FSMContext):
    if not await guard(c):return
    await state.clear();await state.set_state(AddCategory.name);await c.message.edit_text('➕ Введи название новой категории:');await c.answer()
@router.message(AddCategory.name)
async def add_category_name(m:Message,state:FSMContext):
    try:cid=db.add_category((m.text or '').strip())
    except:return await m.answer('Такая категория уже существует.')
    await state.clear();await m.answer(f'✅ Категория #{cid} создана.',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📁 Категории',callback_data='adm:categories')]]))
@router.callback_query(F.data.startswith('adm:cat:'))
async def adm_cat(c:CallbackQuery):
    if not await guard(c):return
    cid=int(c.data.split(':')[2]);x=db.get_category(cid)
    if not x:return await c.answer('Не найдена',show_alert=True)
    text=f'📁 <b>{escape(x["name"])}</b>\n\n{escape(x["description"] or "—")}\n\nСтатус: {"🟢 активна" if x["active"] else "🔴 скрыта"}'
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='👁 Скрыть' if x['active'] else '👁 Включить',callback_data=f'adm:togglecat:{cid}')],[InlineKeyboardButton(text='⬅️ Категории',callback_data='adm:categories')]])
    await c.message.edit_text(text,reply_markup=kb);await c.answer()
@router.callback_query(F.data.startswith('adm:togglecat:'))
async def toggle_cat(c:CallbackQuery):
    if not await guard(c):return
    db.toggle_category(int(c.data.split(':')[2]));await c.answer('Статус изменён');await adm_categories(c)

@router.callback_query(F.data.startswith('adm:users:'))
async def adm_users(c:CallbackQuery):
    if not await guard(c):return
    page=int(c.data.rsplit(':',1)[1]);items=db.users();start=page*ADMIN_PAGE_SIZE;chunk=items[start:start+ADMIN_PAGE_SIZE];rows=[]
    for u in chunk:
        name=('@'+u['username']) if u['username'] else (' '.join(x for x in [u['first_name'],u['last_name']] if x) or str(u['telegram_id']))
        rows.append([InlineKeyboardButton(text=f'{name[:24]} · {fmt_money(u["balance"])}',callback_data=f'adm:user:{u["telegram_id"]}')])
    nav=[]
    if page:nav.append(InlineKeyboardButton(text='◀️',callback_data=f'adm:users:{page-1}'))
    if start+ADMIN_PAGE_SIZE<len(items):nav.append(InlineKeyboardButton(text='▶️',callback_data=f'adm:users:{page+1}'))
    if nav:rows.append(nav)
    rows.append([InlineKeyboardButton(text='⬅️ Админка',callback_data='adm:home')]);await c.message.edit_text(f'👥 <b>ПОЛЬЗОВАТЕЛИ</b> · {len(items)}\n\nВыбери пользователя:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows));await c.answer()

def user_kb(uid):return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='ℹ️ Действия',callback_data=f'adm:userinfo:{uid}')],[InlineKeyboardButton(text='💰 Изменить баланс',callback_data=f'adm:balance:{uid}')],[InlineKeyboardButton(text='⬅️ Пользователи',callback_data='adm:users:0')]])
@router.callback_query(F.data.startswith('adm:user:'))
async def adm_user(c:CallbackQuery):
    if not await guard(c):return
    uid=int(c.data.split(':')[2]);u=db.get_user(uid)
    if not u:return await c.answer('Не найден',show_alert=True)
    name=' '.join(x for x in [u['first_name'],u['last_name']] if x) or '—';username='@'+u['username'] if u['username'] else '—'
    text=f'👤 <b>{escape(name)}</b>\n\nUsername: {escape(username)}\n🆔 <code>{uid}</code>\n💰 Баланс: <b>{fmt_money(u["balance"])}</b>\n📅 Регистрация: {fmt_date(u["created_at"])}\n🕒 Активность: {fmt_date(u["last_seen_at"])}'
    await c.message.edit_text(text,reply_markup=user_kb(uid));await c.answer()
@router.callback_query(F.data.startswith('adm:userinfo:'))
async def adm_userinfo(c:CallbackQuery):
    if not await guard(c):return
    uid=int(c.data.split(':')[2]);acts=db.actions(uid,12);lines=['ℹ️ <b>ПОСЛЕДНИЕ ДЕЙСТВИЯ</b>','']
    for a in acts:lines.append(f'• {fmt_date(a["created_at"])} — <b>{escape(a["action_type"])}</b>\n  {escape(a["details"] or "")[:180]}')
    await c.message.edit_text('\n'.join(lines),reply_markup=user_kb(uid));await c.answer()
@router.callback_query(F.data.startswith('adm:balance:'))
async def adm_balance(c:CallbackQuery,state:FSMContext):
    if not await guard(c):return
    uid=int(c.data.split(':')[2]);await state.set_state(AdminBalance.amount);await state.update_data(uid=uid);await c.message.edit_text('💰 Введи изменение баланса.\n\nНапример: <code>500</code> — добавить 500 ₽\n<code>-100</code> — списать 100 ₽');await c.answer()
@router.message(AdminBalance.amount)
async def adm_balance_amount(m:Message,state:FSMContext):
    d=await state.get_data()
    try:delta=float((m.text or '').replace(',','.'))
    except:return await m.answer('Введи число, например 500 или -100.')
    new=db.change_balance(d['uid'],delta);db.add_action(m.from_user.id,'admin_balance_change',f'Пользователь {d["uid"]}: {delta:+.2f} RUB')
    await state.clear();await m.answer(f'✅ Баланс изменён. Новый баланс: <b>{fmt_money(new)}</b>',reply_markup=user_kb(d['uid']))

@router.callback_query(F.data=='adm:stats')
async def adm_stats(c:CallbackQuery):
    if not await guard(c):return
    s=db.stats();text=(f'📊 <b>СТАТИСТИКА</b>\n\n👥 Пользователи: <b>{s["users"]}</b>\n🛍 Товары: <b>{s["products"]}</b>\n🟢 Активных товаров: <b>{s["active_products"]}</b>\n📁 Категории: <b>{s["categories"]}</b>\n🧾 Покупки: <b>{s["purchases"]}</b>\n💰 Выручка: <b>{fmt_money(s["revenue"])}</b>\n💳 Денег на балансах: <b>{fmt_money(s["balance"])}</b>')
    await c.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⬅️ Админка',callback_data='adm:home')]]));await c.answer()

@router.message()
async def any_message(m:Message):
    if not db.get_user(m.from_user.id):db.upsert_user(m.from_user.id,m.from_user.username,m.from_user.first_name,m.from_user.last_name)
    text=m.text or m.caption or '';db.add_message(m.from_user.id,m.message_id,'incoming',str(m.content_type),text[:4000])

async def run_bot():
    dp=Dispatcher();dp.include_router(router);await bot.delete_webhook(drop_pending_updates=True);await dp.start_polling(bot)
