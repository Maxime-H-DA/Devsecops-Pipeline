FROM gcc:16@sha256:43978d7710a803d1c3d32f4117c1528ec7285a4ce2c0a51e982ec1a6e3d87d95 AS compilation

WORKDIR /app
COPY rpg-source/ .
RUN g++ -std=c++17 -Wall -o rpg_game main.cpp

FROM alpine:3.24.2@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6

WORKDIR /app
COPY --from=compilation /app/rpg_game .
COPY --from=compilation /app/items.csv .
COPY --from=compilation /app/monsters.csv .

RUN apk add --no-cache libstdc++

RUN adduser -D -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

CMD ["./rpg_game"]
