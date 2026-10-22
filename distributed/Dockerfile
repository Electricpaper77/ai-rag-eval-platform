FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod main.go ./
RUN CGO_ENABLED=0 go build -trimpath -o /worker .
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /worker /worker
USER nonroot:nonroot
ENTRYPOINT ["/worker"]
