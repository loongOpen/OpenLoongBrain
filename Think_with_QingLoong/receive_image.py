from flask import Flask, request, jsonify
import os

app = Flask(__name__)

UPLOAD_FOLDER = './upload'  # 定义文件目录，不存在则创建
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


@app.route('/upload', methods=['POST'])  # 定义路由，当客户端发送POST请求到/upload时，这个函数会被调用。
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file:
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        return jsonify({'success': True, 'filepath': filepath}), 200


@app.route('/files', methods=['GET'])  # 定义路由，当客户端发送GET请求到/files时，这个函数会被调用。
def list_files():
    files = os.listdir(UPLOAD_FOLDER)
    return jsonify({'files': files})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
