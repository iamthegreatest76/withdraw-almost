import asyncio
import requests
from aiogram import types, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

taken_slips = {}
OTHER_GROUP_ID = -1002549509706
API_URL = "http://127.0.0.1:9999/act"

class UTRState(StatesGroup):
    waiting_for_utr = State()
    waiting_for_rejection_reason = State()
    waiting_for_photo = State()

def extract_ref_and_hash(text):
    ref = None
    hsh = None
    for line in text.splitlines():
        if line.startswith("#REF:"):
            ref = line.split(":")[1].strip()
        elif line.startswith("#HASH:"):
            hsh = line.split(":")[1].strip()
    return ref, hsh

def register_handlers(dp: Dispatcher, bot):

    @dp.callback_query(lambda c: c.data == "take_slip")
    async def handle_take_slip(callback: types.CallbackQuery, state: FSMContext):
        message = callback.message
        user = callback.from_user
        msg_id = message.message_id
        group_id = message.chat.id
        key = f"{group_id}_{msg_id}"

        if key in taken_slips:
            try: await callback.answer("❌ Already taken.")
            except: pass
            return

        taken_slips[key] = {
            "by": user.id,
            "text": message.text,
            "dm_msg_id": None,
            "dm_delete_ids": []
        }

        sent = await bot.send_message(
            user.id,
            f"🧾 Your assigned slip:\n\n{message.text}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Approve", callback_data=f"approve|{group_id}|{msg_id}")],
                [InlineKeyboardButton(text="❌ Reject", callback_data=f"reject|{group_id}|{msg_id}")]
            ])
        )
        taken_slips[key]["dm_msg_id"] = sent.message_id
        taken_slips[key]["dm_delete_ids"].append(sent.message_id)

        try:
            await message.edit_text(message.text + f"\n\n🔄 Processing by @{user.username or user.first_name}")
        except: pass
        try: await callback.answer("✅ Sent to your DM.")
        except: pass

    @dp.callback_query(lambda c: c.data.startswith("approve|"))
    async def start_utr_entry(callback: types.CallbackQuery, state: FSMContext):
        _, group_id, msg_id = callback.data.split("|")
        await state.set_state(UTRState.waiting_for_utr)
        await state.update_data(group_id=group_id, msg_id=msg_id, action="approve")
        sent = await callback.message.answer("📥 Enter 12-digit UTR:")
        key = f"{group_id}_{msg_id}"
        taken_slips[key]["dm_delete_ids"].append(sent.message_id)

    @dp.callback_query(lambda c: c.data.startswith("reject|"))
    async def start_rejection(callback: types.CallbackQuery, state: FSMContext):
        _, group_id, msg_id = callback.data.split("|")
        await state.set_state(UTRState.waiting_for_rejection_reason)
        await state.update_data(group_id=group_id, msg_id=msg_id, action="reject")

        sent = await callback.message.answer(
            "❌ Choose rejection reason:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Bank server down", callback_data="reason|Bank server down")],
                [InlineKeyboardButton(text="Invalid details", callback_data="reason|Invalid details")],
                [InlineKeyboardButton(text="IFSC wrong", callback_data="reason|IFSC wrong")]
            ])
        )
        await state.update_data(reason_msg_id=sent.message_id)
        key = f"{group_id}_{msg_id}"
        taken_slips[key]["dm_delete_ids"].append(sent.message_id)

    @dp.callback_query(lambda c: c.data.startswith("reason|"))
    async def receive_rejection_reason(callback: types.CallbackQuery, state: FSMContext):
        reason = callback.data.split("|")[1]
        await state.update_data(reason=reason)
        await state.set_state(UTRState.waiting_for_photo)
        sent = await callback.message.answer("📷 Send screenshot for rejection proof:")
        data = await state.get_data()
        key = f"{data.get('group_id', '0')}_{data.get('msg_id', '0')}"
        if key in taken_slips:
            taken_slips[key]["dm_delete_ids"].append(sent.message_id)

    @dp.message(UTRState.waiting_for_utr)
    async def receive_utr(message: types.Message, state: FSMContext):
        data = await state.get_data()
        group_id = data.get("group_id", "0")
        msg_id = data.get("msg_id", "0")
        key = f"{group_id}_{msg_id}"

        if not message.text or not message.text.strip().isdigit() or len(message.text.strip()) != 12:
            reply = await message.reply("❌ Invalid UTR. Send exactly 12 digits.")
            if key in taken_slips:
                taken_slips[key]["dm_delete_ids"].extend([message.message_id, reply.message_id])
            return

        await state.update_data(utr=message.text.strip())
        await state.set_state(UTRState.waiting_for_photo)
        sent = await message.reply("📷 Now send the payment screenshot:")
        if key in taken_slips:
            taken_slips[key]["dm_delete_ids"].extend([message.message_id, sent.message_id])

    @dp.message(UTRState.waiting_for_photo)
    async def receive_photo(message: types.Message, state: FSMContext):
        if not message.photo:
            reply = await message.reply("⚠️ Please send a valid image/photo.")
            return

        data = await state.get_data()
        group_id = int(data.get("group_id", 0))
        msg_id = int(data.get("msg_id", 0))
        key = f"{group_id}_{msg_id}"
        if key not in taken_slips:
            await message.reply("⚠️ Slip expired or not found.")
            return

        original_text = taken_slips[key]["text"]
        username = message.from_user.username or message.from_user.first_name
        photo_id = message.photo[-1].file_id
        ref, hsh = extract_ref_and_hash(original_text)

        success = False
        try:
            if data["action"] == "approve":
                utr = data.get("utr", "N/A")
                status_text = f"✅ Approved by @{username}\nUTR: {utr}\n📷 Screenshot attached"
                r = requests.post(API_URL, json={"action": "approve", "ref": ref, "hash": hsh, "utr": utr})
                success = r.ok
            else:
                reason = data.get("reason", "No reason")
                status_text = f"❌ Rejected by @{username}\nReason: {reason}\n📷 Screenshot attached"
                r = requests.post(API_URL, json={"action": "reject", "ref": ref, "hash": hsh, "reason": reason})
                success = r.ok
        except Exception as e:
            print(f"[❌ POST Failed] {e}")
            success = False

        if not success:
            await message.reply("❌ Failed to perform action on website. Please try again.")
            return

        final_text = f"{original_text}\n\n{status_text}"

        await bot.send_photo(chat_id=OTHER_GROUP_ID, photo=photo_id, caption=final_text)

        try:
            await bot.edit_message_text(chat_id=group_id, message_id=msg_id, text=final_text)
        except: pass

        try:
            await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=taken_slips[key]["dm_msg_id"], reply_markup=None)
        except: pass

        try:
            if "reason_msg_id" in data:
                await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=data["reason_msg_id"], reply_markup=None)
        except: pass

        taken_slips[key]["dm_delete_ids"].append(message.message_id)
        final_notice = await message.reply("✅ Done. Cleaning messages in 3 seconds...")
        taken_slips[key]["dm_delete_ids"].append(final_notice.message_id)

        await asyncio.sleep(3)
        for mid in taken_slips[key]["dm_delete_ids"]:
            try: await bot.delete_message(chat_id=message.chat.id, message_id=mid)
            except: continue

        await state.clear()
