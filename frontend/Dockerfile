# Development image for the Vite dev server. Production build/serve is handled
# in Phase 18 (AWS deployment).
FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
