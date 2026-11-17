"""Bot qaysi qadamda turganini eslab qoladi (FSM)."""

from aiogram.fsm.state import State, StatesGroup


class Flow(StatesGroup):
    wait_file = State()
    collect_images = State()
    collect_merge = State()
    wait_pages = State()
    wait_angle = State()
    choose_action = State()
    edit_menu = State()
    edit_name = State()
    edit_thumb = State()
    wait_receipt = State()
    admin_text = State()


INPUT_STATES = {
    Flow.edit_name.state,
    Flow.wait_pages.state,
    Flow.admin_text.state,
}

CONVERT_ACTIONS = {"pdf2word", "word2pdf", "img2pdf", "pdf2img"}
TOOL_ACTIONS = {"merge", "split", "compress", "delete", "rotate"}

PROMPTS = {
    "pdf2word": "ask_pdf",
    "word2pdf": "ask_word",
    "pdf2img": "ask_pdf",
    "compress": "ask_pdf",
    "split": "ask_pdf",
    "delete": "ask_pdf",
    "rotate": "ask_pdf",
    "edit": "ask_any_file",
}

ACTION_LABELS = {
    "pdf2word": "act_pdf2word",
    "word2pdf": "act_word2pdf",
    "img2pdf": "act_img2pdf",
    "pdf2img": "act_pdf2img",
    "merge": "act_merge",
    "split": "act_split",
    "compress": "act_compress",
    "delete": "act_delete",
    "rotate": "act_rotate",
    "rename": "act_rename",
}
