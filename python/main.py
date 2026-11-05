
from warcio.warcwriter import WARCWriter
from warcio.statusandheaders import StatusAndHeaders
import requests
import pathlib
import time

def url_list_generator():
    directory = []

    work_dir = pathlib.Path("app")

    for item in work_dir.rglob("*.*"):
        directory.append(str(item))

    return directory
     
def warc_generator(site_name,   domain):
    output_directory = url_list_generator()

    with open('output/' + site_name + '_archive.warc.gz', 'wb') as output:
        writer = WARCWriter(output, gzip=True)
        for page in output_directory:
            url = "http://host.docker.internal:8080/" + page.replace("app/",    "")
            warc_url = domain + page.replace("app/",    "")
            resp = requests.get(url,
                                headers={'Accept-Encoding': 'identity'},
                                stream=True)

            # get raw headers from urllib3
            headers_list = resp.raw.headers.items()

            http_headers = StatusAndHeaders('200 OK', headers_list, protocol='HTTP/1.0')

            record = writer.create_warc_record(warc_url, 'response',
                                                payload = resp.raw,
                                                http_headers=http_headers)

            writer.write_record(record)
            
    print(str(len(output_directory)) + " pages processed")

if __name__ == '__main__':
    start_time = time.time()
    site_name = "WarburgOmeka"  # To be used in WARC filename
    domain = "https://omeka.warburg.sas.ac.uk/"  # To be used for WARC-Target-URIs,
    # i.e. the address that you will navigate to when replaying the WARC
    warc_generator(site_name, domain)
    print("--- %s seconds to run ---" % (time.time() - start_time))
