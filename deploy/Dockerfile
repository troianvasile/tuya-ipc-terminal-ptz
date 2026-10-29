FROM golang:1.23-alpine AS build
WORKDIR /src
RUN apk add --no-cache git
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -o /tuya-ipc-terminal .

FROM python:3.12-alpine
RUN addgroup -S bridge && adduser -S -G bridge bridge \
    && pip install --no-cache-dir "qrcode==8.2" "pillow==11.3.0"
COPY --from=build /tuya-ipc-terminal /usr/local/bin/tuya-ipc-terminal
COPY deploy/manage.py /usr/local/bin/manage.py
WORKDIR /data
RUN chown bridge:bridge /data
USER bridge
ENV PYTHONUNBUFFERED=1
CMD ["python3", "/usr/local/bin/manage.py"]
