import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import configs

CERT = sys.argv[1]

def deleteCertJson():
    cert_data = configs.getcertData()

    if CERT in cert_data:
        configs.deleteSectionItem("certs", CERT)
        print(CERT + " configuration deleted")
    else:
        print(CERT + " configuration not found")

if __name__ == "__main__":
    deleteCertJson()
