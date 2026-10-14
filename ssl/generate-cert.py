import argparse
import ipaddress
from pathlib import Path
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

parser=argparse.ArgumentParser()
parser.add_argument('--ip',required=True)
parser.add_argument('--directory',default='/ssl/certs')
args=parser.parse_args()
ip=ipaddress.ip_address(args.ip)
out=Path(args.directory);out.mkdir(parents=True,exist_ok=True)
now=datetime.now(timezone.utc)
def write_key(path,key):
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    path.chmod(0o600)
ca_key_path=out/'root-ca.key';ca_cert_path=out/'root-ca.crt'
if ca_key_path.exists() != ca_cert_path.exists():
    raise SystemExit('Incomplete CA files. Restore both root-ca.key and root-ca.crt before continuing.')
if ca_key_path.exists():
    ca_key=serialization.load_pem_private_key(ca_key_path.read_bytes(),password=None)
    ca=x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
    if ca.not_valid_after_utc <= now+timedelta(days=366):
        raise SystemExit('CA expires too soon; arrange CA renewal before generating the server certificate.')
else:
    ca_key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'MOMCC PROD Portal Local Root CA')])
    ca=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=3650)).add_extension(x509.BasicConstraints(ca=True,path_length=0),True).add_extension(x509.KeyUsage(digital_signature=True,key_encipherment=False,key_cert_sign=True,crl_sign=True,content_commitment=False,data_encipherment=False,key_agreement=False,encipher_only=None,decipher_only=None),True).add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),False).sign(ca_key,hashes.SHA256()))
    write_key(ca_key_path,ca_key);ca_cert_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,str(ip))])
cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=365)).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip)]),False).add_extension(x509.BasicConstraints(ca=False,path_length=None),True).add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),False).add_extension(x509.KeyUsage(digital_signature=True,key_encipherment=True,key_cert_sign=False,crl_sign=False,content_commitment=False,data_encipherment=False,key_agreement=False,encipher_only=None,decipher_only=None),True).add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),False).sign(ca_key,hashes.SHA256()))
write_key(out/'server.key',key)
(out/'server.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
(out/'root-ca.cer').write_bytes(ca.public_bytes(serialization.Encoding.DER))
print('Certificate generated for IP:',ip)
print('Server certificate expires:',cert.not_valid_after_utc.isoformat())
print('Root CA SHA256 fingerprint:',ca.fingerprint(hashes.SHA256()).hex())
print('Share only root-ca.cer with agents. Keep all .key files private.')
