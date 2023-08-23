import fitz
import os
import glob
import re
import sys
import multiprocessing
import hashlib
import mysql.connector
import logging
from tqdm import tqdm
from rich.progress import Progress
import colorama
from colorama import Fore, Style

pola_0 = re.compile(r'^\d{1,3}$')
pola_1 = re.compile(r'^[a-zA-Z\s\'-`.]{3,}$')
pola_2 = re.compile(r'^[LP]$')
pola_3 = re.compile(r'^\d{1,3}$')
pola_4 = re.compile(r'^(?:[a-zA-Z\s,.\'-]+|)$')
pola_5 = re.compile(r'^\d{3}$')
pola_6 = re.compile(r'^\d{3}$')
pola_unknown = re.compile(r'[^\x00-\x7F]+')
kabko = "KAB. "

from colorama import Fore, Style, init

def generate_unique_id(data):
    hash_object = hashlib.sha256(data.encode())
    unique_id = hash_object.hexdigest()
    return unique_id

def save_to_database(data_row, cursor):
    insert_query = """
    INSERT INTO pemilih (id, no, nama, jk, usia, alamat, rt, rw, provinsi, kabupaten, kecamatan, kelurahan, tps)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
    id = id
    """

    try:
        cursor.execute(insert_query, data_row)
    except mysql.connector.Error as err:
        logging.error(f"Error saving data: {err} {data_row}")

def process_pdf(pdf_path):
    result = []
    total_pages = fitz.open(pdf_path).page_count
    provinsi= ''
    kabupaten= ''
    kecamatan= ''
    kelurahan= ''
    tps= ''
    pemilih=[]

    for page_number in range(1, total_pages + 1):
        try:
            lines = extract_table_text(pdf_path, page_number).splitlines()
            start = 0
            end = 10000
            data = []


            if lines and lines[0].strip() == "PROVINSI" and len(lines) > 13:
                provinsi = lines[1].split(':', 1)[1].strip()
                kabupaten = kabko +  lines[4].split(':', 1)[1].strip()
                kecamatan = lines[2].split(':', 1)[1].strip()
                kelurahan = lines[5].split(':', 1)[1].strip()
                tps = lines[6].split(':', 1)[1].strip()
                for index, item in enumerate(lines):
                    if index > start and item == '8' and lines[index - 1] == '7' and lines[index - 2] == '6':
                        start = index + 1
                    if index < end and item.strip() == 'TPS':
                        end = index
                    if index < end and item.split()[0] == 'TAHUN':
                        end = index
                    if index < end and item.split()[0] == 'Halaman':
                        end = index

            else:
                if len(lines) > 13:
                    for index, item in enumerate(lines):
                        if index > start and item == 'Keterangan':
                            start = index + 1
                        if index > start and item == 'KET.' and lines[index - 1] == 'RW':
                            start = index + 1
                        if index < end and item.split()[0].strip() == 'DITETAPKAN' and re.match(pola_6, lines[index - 1]):
                            end = index
                        if index < end and item.split()[0].strip() == 'DITETAPKAN':
                            end = index - 1
                        if index < end and item.split()[0] == 'Halaman':
                            end = index
                        if index < end and item.split()[0] == 'TPS':
                            end = index
                        if index < end and item.split()[0] == 'TAHUN':
                            end = index
                        

            if end - start > 6 and end != 10000:
                data = lines[start:end]
            i = 0
           

            while i < len(data):
                check_data = data[i:i+7]
                checked_data = check_data
                n_err = 0
                
                if (pola_0.match(check_data[0]) and
                    pola_1.match(check_data[1]) and
                    pola_2.match(check_data[2]) and
                    pola_3.match(check_data[3]) and
                    pola_4.match(check_data[4]) and
                    pola_5.match(check_data[5]) and
                    pola_6.match(check_data[6])):
                    i += 7
                else:
                    if not pola_0.match(checked_data[0]):
                        parts = check_data[0].split(maxsplit=1)
                        checked_data[0] = parts[0]
                        checked_data.insert(1, parts[1])
                        if len(checked_data) > 7:
                            checked_data = checked_data[:-1]
                        n_err += 1

                    if not pola_1.match(checked_data[1]):
                        if pola_unknown.search(checked_data[1]):
                            checked_data[1] = re.sub(r'[^\x00-\x7F]+', '', checked_data[1])


                    if not pola_2.match(checked_data[2]):
                        if  re.search(r'[PL]$', checked_data[1]):
                            gr = re.match(r'^(.*)(.)\s*$', checked_data[1])
                            checked_data[1] = gr.group(1)
                            checked_data.insert(2, gr.group(2))
                            if len(checked_data) > 7:
                                checked_data = checked_data[:-1]
                            n_err += 1


                    if not pola_4.match(checked_data[4]):
                        match = re.search(r'(.*?)(\d+)$', checked_data[4])
                        mm = [match.group(1).strip(), match.group(2)]
                        checked_data[4] = mm[0]
                        checked_data.insert(5, mm[1])
                        if len(checked_data) > 7:
                            checked_data = checked_data[:-1]
                        n_err += 1

                    i += 7 - n_err

                unique_id = generate_unique_id(f"{checked_data}")
                checked_data.extend([provinsi, kabupaten, kecamatan, kelurahan, tps])
                checked_data.insert(0, unique_id)
                pemilih.append(checked_data)

        except Exception as e:
            print(f"{Fore.RED}{Style.BRIGHT}Error processing file: {pdf_path} page: {page_number} {Style.RESET_ALL}")
            print(f"{Fore.RED}{Style.BRIGHT}Error message: {e}{Style.RESET_ALL}")
            continue  

    db = mysql.connector.connect(
        host="127.0.2.3",
        user="root",
        password="Kalimangg1s",
        database="pemiludb"
    )
 

    with db.cursor() as cursor:
        for row in pemilih:
            save_to_database(row, cursor)

    db.commit()
    db.close()

def extract_table_text(pdf_path, page_number):
    doc = fitz.open(pdf_path)
    page = doc[page_number - 1]
    text = page.get_text("text")
    return text

def main():
    init(autoreset=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    root_folder = "data"
    pdf_files = glob.glob(os.path.join(root_folder, "**/*.pdf"), recursive=True)

    total_files = len(pdf_files)
    with multiprocessing.Pool() as pool:
        with tqdm(total=total_files, desc=f"{Fore.CYAN}Processing PDFs...{Style.RESET_ALL}") as progress:
            processed_count = 0
            for _ in pool.imap_unordered(process_pdf, pdf_files):
                progress.update()
                processed_count += 1
                progress.set_postfix({"Processed": processed_count, "Total": total_files})
                progress.refresh()

if __name__ == "__main__":
    main()