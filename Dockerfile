FROM python:3.7.0
RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app
COPY requirements.txt /usr/src/app
RUN pip install pip --upgrade && pip install -r requirements.txt
COPY ./main.py /usr/src/app/main.py
ENTRYPOINT ["python3"]
CMD ["main.py"]