# Multi-stage build per Document 7 §17.3. Build context must be the monorepo
# ROOT (pnpm workspace deps), invoked as: docker build -f apps/web/Dockerfile .

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/
COPY packages/ui/package.json ./packages/ui/
COPY packages/config/package.json ./packages/config/
RUN corepack enable && pnpm install --frozen-lockfile

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN corepack enable && pnpm --filter @investiq/web build

FROM node:20-alpine AS runtime
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /app/apps/web/public ./apps/web/public
USER appuser
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
