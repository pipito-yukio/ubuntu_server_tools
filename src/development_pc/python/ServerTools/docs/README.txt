# python仮想環境の作成 for ubuntu 24.04
# python3-venvライブラリがシステムにインストール済みであること
# $ sudo apt install python3-venv 

$ python3 -m venv py_psycopg2 
$ . py_psycopg2/bin/activate
# Psycopg2 ライブラリインストール
(py_psycopg2)$ pip install psycopg2-binary

