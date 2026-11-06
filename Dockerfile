FROM gcc:16@sha256:43978d7710a803d1c3d32f4117c1528ec7285a4ce2c0a51e982ec1a6e3d87d95 AS compilation

WORKDIR /app
COPY rpg-source/ .
RUN g++ -std=c++17 -Wall -o rpg_game main.cpp

FROM alpine:3.24.3@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a

WORKDIR /app
COPY --from=compilation /app/rpg_game .
COPY --from=compilation /app/items.csv .
COPY --from=compilation /app/monsters.csv .

RUN apk add --no-cache libstdc++

RUN adduser -D -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

CMD ["./rpg_game"]
