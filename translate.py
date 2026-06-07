import os
import requests
import argparse
from lxml import etree
from tqdm import tqdm

# === НАСТРОЙКИ ===
API_URL = "http://localhost:8085/v1/chat/completions"
MODEL_NAME = "Qwen3.6-35B-A3B-uncensored-heretic-Q4_K_M.gguf"
SRC_LANG = "Russian"
TARGET_LANG = "English"

# Лимиты в символах (для грубого подсчета: 1 токен кириллицы ~ 3-4 символа)
CHUNK_SIZE_CHARS = 5000     # Примерно 1300-1500 токенов для перевода
CONTEXT_SIZE_CHARS = 1800   # Примерно 450-500 токенов истории для контекста

# Флаг-разделитель, по которому ЛЛМ поймет, где контекст, а где работа
DELIMITER = "=== TARGET_TRANSLATION_ZONE ==="

# === ПРОМПТЫ ===
PROMPT_PASS_1 = (
    f"You are an expert book translator from {SRC_LANG} to {TARGET_LANG}.\n"
    f"TASK: Translate ONLY the text inside the section marked with '{DELIMITER}'.\n"
    f"CRITICAL RULES:\n"
    f"1. Anything BEFORE '{DELIMITER}' is provided ONLY for story context. DO NOT translate or include it in the output!\n"
    f"2. Preserve all XML tags (e.g., <emphasis>, <strong>) exactly in their relative positions.\n"
    f"3. Output ONLY the translated blocks from the target zone. No explanations, no markdown chat formatting."
)

PROMPT_PASS_2 = (
    f"You are a master literary editor.\n"
    f"TASK: Improve the style, flow, and vocabulary of the rough translation inside '{DELIMITER}' so it reads naturally and idiomatically in {TARGET_LANG}\n"
    f"CRITICAL RULES:\n"
    f"1. Use the 'Original text' for nuance and the 'Context' to maintain continuity.\n"
    f"2. You must preserve all XML tags exactly as they appear in the rough translation.\n"
    f"3. Output ONLY the refined translation from the target zone. No explanations."
)

def call_llm(system_prompt: str, user_content: str) -> str:
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.25,
    }
    for attempt in range(3):
        try:
            response = requests.post(API_URL, json=payload, timeout=120)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'].strip()
        except requests.exceptions.RequestException:
            if attempt == 2:
                print("\n[Внимание] ЛЛМ не ответила, возвращаем оригинал.")
    return ""

def build_chunks(elements):
    """Группирует XML-элементы в чанки по объему текста"""
    chunks = []
    current_chunk = []
    current_length = 0
    
    for idx, el, text in elements:
        current_chunk.append((idx, el, text))
        current_length += len(text)
        
        # Если превысили лимит, закрываем чанк на этом абзаце
        if current_length >= CHUNK_SIZE_CHARS:
            chunks.append(current_chunk)
            current_chunk = []
            current_length = 0
            
    if current_chunk:
        chunks.append(current_chunk)
    return chunks

def extract_text_with_tags(element) -> str:
    """Извлекает текст элемента со всеми внутренними тегами"""
    return (element.text or "") + "".join(etree.tostring(child, encoding='utf-8').decode('utf-8') for child in element)

def update_xml_elements(chunk_elements, translated_texts):
    """Безопасно упаковывает переведенные строки обратно в XML структуру"""
    for (idx, el, _), text_out in zip(chunk_elements, translated_texts):
        try:
            wrapped_xml = f"<p>{text_out}</p>"
            new_el = etree.fromstring(wrapped_xml.encode('utf-8'))
            el.clear()
            el.text = new_el.text
            for child in new_el:
                el.append(child)
        except etree.XMLSyntaxError:
            # План Б: если ЛЛМ сломала теги, пишем чистый текст
            clean_text = text_out.replace("<", "&lt;").replace(">", "&gt;")
            el.clear()
            el.text = clean_text

def translate_fb2_with_context(input_path: str, output_path: str):
    if not os.path.exists(input_path):
            print(f"Ошибка: Входной файл '{input_path}' не найден!")
            return
            
    print("Парсинг FB2 книги...")
    parser = etree.XMLParser(recover=True, remove_blank_text=True)
    tree = etree.parse(input_path, parser=parser)
    root = tree.getroot()
    
    ns = {"fb": root.nsmap.get(None) or "http://www.gribuser.ru/xml/fictionbook/2.0"}
    raw_elements = root.xpath("//fb:p | //fb:v | //fb:subtitle", namespaces=ns)
    
    # Индексируем элементы, чтобы точно знать, куда возвращать перевод
    indexed_elements = [(i, el, extract_text_with_tags(el)) for i, el in enumerate(raw_elements)]
    
    # Режем на чанки
    chunks = build_chunks(indexed_elements)
    print(f"Книга разбита на {len(chunks)} чанков.")
    
    # Хранилища для скользящего контекста (храним плоский текст)
    history_src = ""
    history_tgt = ""
    
    for i, chunk in enumerate(tqdm(chunks, desc="Перевод чанков")):
        # Формируем тело текущего чанка для отправки (каждый абзац с новой строки)
        target_src_payload = "\n".join([item[2] for item in chunk])
        
        # --- ПРОХОД 1: Перевод с контекстом предыдущих глав ---
        input_pass1 = ""
        if history_src and history_tgt:
            input_pass1 += f"--- PREVIOUS STORY CONTEXT (DO NOT TRANSLATE) ---\n"
            input_pass1 += f"Original: {history_src[-CONTEXT_SIZE_CHARS:]}\n"
            input_pass1 += f"Translation: {history_tgt[-CONTEXT_SIZE_CHARS:]}\n\n"
        
        input_pass1 += f"{DELIMITER}\n{target_src_payload}"
        
        translated_payload = call_llm(PROMPT_PASS_1, input_pass1)
        
        # Если ЛЛМ выдала пустую строку или сбой — страхуемся оригиналом
        if not translated_payload.strip():
            translated_payload = target_src_payload
            
        # --- ПРОХОД 2: Литературный Оверлей (Стиль) ---
        input_pass2 = ""
        if history_tgt:
            input_pass2 += f"--- CONTEXT FOR STYLE CONTINUITY ---\n{history_tgt[-CONTEXT_SIZE_CHARS:]}\n\n"
        
        input_pass2 += f"Original text:\n{target_src_payload}\n\n"
        input_pass2 += f"{DELIMITER}\nRough Translation:\n{translated_payload}"
        
        final_payload = call_llm(PROMPT_PASS_2, input_pass2)
        if not final_payload.strip():
            final_payload = translated_payload
            
        # Сплитуем полученный перевод обратно на абзацы
        translated_lines = final_payload.split("\n")
        
        # Если ЛЛМ «склеила» строки или выдала не то количество абзацев, 
        # выравниваем списки, чтобы не поплыла верстка книги
        if len(translated_lines) != len(chunk):
            if len(translated_lines) > len(chunk):
                translated_lines = translated_lines[:len(chunk)]
            else:
                while len(translated_lines) < len(chunk):
                    translated_lines.append(chunk[len(translated_lines)][2]) # дублируем оригинал при нехватке
        
        # Записываем перевод обратно в XML структуру текущего чанка
        update_xml_elements(chunk, translated_lines)
        
        # Обновляем скользящую историю для следующего чанка
        history_src += "\n" + target_src_payload
        history_tgt += "\n" + "\n".join(translated_lines)
        
        # Периодический автосейв дерева (базовый чекпоинт на случай выключения света/железа)
        if i % 10 == 0:
            with open(output_path, "wb") as f:
                tree.write(f, encoding="utf-8", xml_declaration=True)

    # Финальное сохранение
    print("Сохранение финальной книги...")
    with open(output_path, "wb") as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)
    print("Перевод успешно завершен!")

if __name__ == "__main__":
    # Настраиваем парсер аргументов командной строки
        parser = argparse.ArgumentParser(description="ЛЛМ-переводчик FB2 книг по чанкам с сохранением контекста.")
        
        # Позиционные (обязательные) аргументы
        parser.add_argument("input", help="Путь к исходному файлу FB2 (например: book.fb2)")
        parser.add_argument("output", help="Путь для сохранения переведенного файла (например: ready.fb2)")
        
        args = parser.parse_args()
        
        # Запускаем перевод с переданными путями
        translate_fb2_with_context(args.input, args.output)