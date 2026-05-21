import sys
import os
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from modules.base import configs


def _arg(index, name):
    try:
        value = sys.argv[index]
    except IndexError:
        raise ValueError("Missing required argument: " + name)
    value = str(value).strip()
    if not value:
        raise ValueError("Empty required argument: " + name)
    return value

def deleteCertJson():
    cert = _arg(1, "CERT")
    cert_data = configs.getcertData()

    if cert in cert_data:
        configs.deleteSectionItem("certs", cert)
        print(cert + " configuration deleted")
    else:
        print(cert + " configuration not found")

if __name__ == "__main__":
    deleteCertJson()
