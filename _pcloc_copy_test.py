# перенос порт-теста шага 6/7 родителя 185 в VPS-зеркало ПК-репо (дев-файл, не рабочие таблицы)
import shutil

SRC = "/root/turbobaby-manager-bot/_pcloc_test_stage.py"
DST = "/root/_pcport_userbot_185/test_pc_local_dec.py"
shutil.copyfile(SRC, DST)
print("copied:", DST)
