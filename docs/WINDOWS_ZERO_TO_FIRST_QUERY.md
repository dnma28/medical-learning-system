# Windows — từ số 0 đến truy vấn đầu tiên

Tài liệu này dành cho người chưa quen Python, Git hoặc terminal.

## Mục tiêu

Chỉ cần đạt một kết quả:

> Costanzo PDF được xử lý và hệ thống trả lời một câu hỏi từ index RAG.

## A. Tải project về máy

Trên GitHub repository `dnma28/medical-learning-system`, chọn **Code → Download ZIP**.

Giải nén ZIP vào một thư mục dễ tìm, ví dụ:

```text
C:\medical-learning-system
```

## B. Cài Python

Cần Python 3.10 trở lên. Sau khi cài, đóng và mở lại cửa sổ Command Prompt.

## C. Chạy setup tự động

Trong thư mục project, chạy:

```text
setup_windows.bat
```

File này sẽ tự:

1. kiểm tra Python;
2. tạo `.venv`;
3. nâng cấp pip;
4. cài project + RAG-Anything;
5. tạo `.env` nếu chưa có;
6. chạy health check.

## D. Thêm API key

Mở file `.env` bằng Notepad.

Tìm:

```text
OPENAI_API_KEY=
```

và thêm key của bạn sau dấu `=`.

Không gửi key này lên GitHub hoặc vào tin nhắn công khai.

## E. Chuẩn bị Costanzo

Giữ PDF ở ngoài repository, ví dụ:

```text
C:\MedicalBooks\Costanzo Physiology 6e.pdf
```

## F. Chạy cuốn sách đầu tiên

Cách dễ nhất: kéo file PDF Costanzo và thả trực tiếp lên:

```text
first_book_windows.bat
```

Hoặc mở Command Prompt trong thư mục project và chạy:

```bat
first_book_windows.bat "C:\MedicalBooks\Costanzo Physiology 6e.pdf"
```

Script sẽ:

1. ingest PDF bằng RAG-Anything;
2. dùng MinerU làm parser mặc định;
3. lưu index trong `rag_storage/` cục bộ;
4. chạy câu hỏi thử về resting membrane potential.

## G. Nếu có lỗi

Dừng tại lỗi đó. Chụp màn hình hoặc copy toàn bộ phần lỗi và gửi lại trong cuộc trò chuyện này.

Không cần tự cài thêm package ngẫu nhiên trước khi xác định nguyên nhân.