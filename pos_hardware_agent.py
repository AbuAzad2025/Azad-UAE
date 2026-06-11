import os
import sys
import json
import socket
import struct
from decimal import Decimal
from http.server import HTTPServer, BaseHTTPRequestHandler

HOST = os.environ.get('POS_HARDWARE_HOST', '127.0.0.1')
PORT = int(os.environ.get('POS_HARDWARE_PORT', '8567'))
PRINTER_IP = os.environ.get('POS_PRINTER_IP', '')
PRINTER_PORT = int(os.environ.get('POS_PRINTER_PORT', '9100'))
CASH_DRAWER_IP = os.environ.get('POS_CASH_DRAWER_IP', '')
CASH_DRAWER_PORT = int(os.environ.get('POS_CASH_DRAWER_PORT', '9100'))


def escpos_init():
    return b'\x1b\x40'


def escpos_align(center=False):
    return b'\x1b\x61\x01' if center else b'\x1b\x61\x00'


def escpos_bold(on=True):
    return b'\x1b\x45\x01' if on else b'\x1b\x45\x00'


def escpos_text_size(w, h):
    return b'\x1d\x21' + bytes([(w - 1) | ((h - 1) << 4)])


def escpos_text(text, encoding='utf-8'):
    return text.encode(encoding, errors='replace')


def escpos_cut():
    return b'\x1d\x56\x00'


def escpos_open_drawer():
    return b'\x10\x14\x01\x00\x05'


def build_receipt_html(sale_data):
    lines = []
    lines.append('<div style="font-family:monospace;font-size:12px;direction:rtl;text-align:right;width:280px;margin:0 auto;padding:8px">')
    lines.append(f'<h3 style="text-align:center;margin:4px 0">{sale_data.get("store_name", "")}</h3>')
    if sale_data.get('sale_number'):
        lines.append(f'<p style="text-align:center;margin:2px 0"><b>فاتورة رقم:</b> {sale_data["sale_number"]}</p>')
    lines.append(f'<p style="text-align:center;margin:2px 0">{sale_data.get("date", "")}</p>')
    lines.append('<hr style="border-top:1px dashed #000">')
    lines.append('<table style="width:100%;font-size:12px">')
    lines.append('<tr><th style="text-align:right">البيان</th><th style="text-align:center">الكمية</th><th style="text-align:left">السعر</th><th style="text-align:left">الإجمالي</th></tr>')
    for item in sale_data.get('items', []):
        name = item.get('name', '')
        qty = item.get('quantity', 0)
        price = item.get('unit_price', 0)
        total = item.get('total', 0)
        lines.append(f'<tr><td style="text-align:right">{name}</td><td style="text-align:center">{qty}</td><td style="text-align:left">{price}</td><td style="text-align:left">{total}</td></tr>')
    lines.append('</table>')
    lines.append('<hr style="border-top:1px dashed #000">')
    lines.append(f'<p style="text-align:left;font-size:14px"><b>الإجمالي: {sale_data.get("total", 0)}</b></p>')
    if sale_data.get('paid_amount'):
        lines.append(f'<p style="text-align:left">المدفوع: {sale_data["paid_amount"]}</p>')
    if sale_data.get('change'):
        lines.append(f'<p style="text-align:left">الباقي: {sale_data["change"]}</p>')
    if sale_data.get('payment_method'):
        lines.append(f'<p style="text-align:left">طريقة الدفع: {sale_data["payment_method"]}</p>')
    if sale_data.get('customer_name'):
        lines.append(f'<p style="text-align:right">العميل: {sale_data["customer_name"]}</p>')
    lines.append('<hr style="border-top:1px dashed #000">')
    lines.append('<p style="text-align:center;font-size:10px">شكراً لتعاملكم معنا</p>')
    lines.append('</div>')
    return '\n'.join(lines)


def build_receipt_escpos(sale_data):
    buf = bytearray()
    buf.extend(escpos_init())
    buf.extend(escpos_align(True))
    buf.extend(escpos_text_size(2, 2))
    buf.extend(escpos_bold(True))
    buf.extend(escpos_text(sale_data.get('store_name', '')[:32]))
    buf.extend(b'\x0a')
    buf.extend(escpos_text_size(1, 1))
    buf.extend(escpos_bold(False))
    if sale_data.get('sale_number'):
        buf.extend(escpos_align(True))
        buf.extend(escpos_text(f'فاتورة: {sale_data["sale_number"]}'))
        buf.extend(b'\x0a')
    if sale_data.get('date'):
        buf.extend(escpos_align(True))
        buf.extend(escpos_text(sale_data['date']))
        buf.extend(b'\x0a')
    buf.extend(b'\x1d\x21\x00')
    buf.extend(b'-' * 32)
    buf.extend(b'\x0a')
    for item in sale_data.get('items', []):
        name = (item.get('name', '') or '')[:20]
        qty = item.get('quantity', 1)
        price = item.get('unit_price', 0)
        total = item.get('total', 0)
        line = f'{name:<20} {qty:>2} x {price:>6} = {total:>8}'
        buf.extend(escpos_text(line))
        buf.extend(b'\x0a')
    buf.extend(b'-' * 32)
    buf.extend(b'\x0a')
    buf.extend(escpos_bold(True))
    buf.extend(escpos_text(f'الإجمالي: {sale_data.get("total", 0):>10}'))
    buf.extend(b'\x0a')
    buf.extend(escpos_bold(False))
    if sale_data.get('paid_amount'):
        buf.extend(escpos_text(f'المدفوع:   {sale_data["paid_amount"]:>10}'))
        buf.extend(b'\x0a')
    if sale_data.get('change'):
        buf.extend(escpos_text(f'الباقي:    {sale_data["change"]:>10}'))
        buf.extend(b'\x0a')
    if sale_data.get('payment_method'):
        buf.extend(escpos_text(f'الدفع:     {sale_data["payment_method"]}'))
        buf.extend(b'\x0a')
    if sale_data.get('customer_name'):
        buf.extend(escpos_text(f'العميل:    {sale_data["customer_name"]}'))
        buf.extend(b'\x0a')
    buf.extend(b'\x0a')
    buf.extend(escpos_align(True))
    buf.extend(escpos_text('شكراً لتعاملكم معنا'))
    buf.extend(b'\x0a\x0a\x0a')
    buf.extend(escpos_cut())
    return bytes(buf)


def send_raw(data, ip, port):
    if not ip:
        return False, 'لم يتم تعيين عنوان IP للطابعة'
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((ip, port))
        sock.sendall(data)
        sock.close()
        return True, None
    except Exception as e:
        return False, str(e)


class HardwareHandler(BaseHTTPRequestHandler):

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path == '/status':
            self._send_json({'status': 'ok', 'printer_ip': PRINTER_IP, 'printer_port': PRINTER_PORT})
        else:
            self._send_json({'error': 'not found'}, 404)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length else b'{}'
        try:
            data = json.loads(body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json({'error': 'invalid JSON'}, 400)
            return

        if self.path == '/print-receipt':
            ip = data.get('printer_ip') or PRINTER_IP
            port = data.get('printer_port') or PRINTER_PORT
            raw = build_receipt_escpos(data)
            ok, err = send_raw(raw, ip, port)
            if ok:
                self._send_json({'status': 'printed'})
            else:
                self._send_json({'error': err}, 500)

        elif self.path == '/open-drawer':
            ip = data.get('drawer_ip') or CASH_DRAWER_IP or PRINTER_IP
            port = data.get('drawer_port') or CASH_DRAWER_PORT or PRINTER_PORT
            ok, err = send_raw(escpos_open_drawer(), ip, port)
            if ok:
                self._send_json({'status': 'opened'})
            else:
                self._send_json({'error': err}, 500)

        elif self.path == '/print-html':
            html = build_receipt_html(data)
            self._send_json({'status': 'html_ready', 'html': html})

        else:
            self._send_json({'error': 'not found'}, 404)

    def log_message(self, format, *args):
        print(f'[POS Hardware] {args[0]} {args[1]} {args[2]}')


def main():
    server = HTTPServer((HOST, PORT), HardwareHandler)
    print(f'POS Hardware Agent running on http://{HOST}:{PORT}')
    print(f'  Printer: {PRINTER_IP or "(not set)"}:{PRINTER_PORT}')
    print(f'  Cash drawer: {CASH_DRAWER_IP or "(uses printer IP)"}:{CASH_DRAWER_PORT}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down...')
        server.server_close()


if __name__ == '__main__':
    main()
