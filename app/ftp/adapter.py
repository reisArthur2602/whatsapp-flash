import logging

from ftplib import FTP
from config import FTP_CONFIG
 
def ftp_upload_adapter(local, remote_dir, name):
    try:
        ftp = FTP(FTP_CONFIG['host'])
        ftp.login(FTP_CONFIG['user'], FTP_CONFIG['password'])
        ftp.cwd(remote_dir)
        with open(local,'rb') as f:
            ftp.storbinary(f"STOR {name}", f)
        ftp.quit()
        return True
    except Exception as e:
        logging.error(f"FTP {remote_dir}: {e}")
        return False