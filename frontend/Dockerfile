FROM node:18-alpine

WORKDIR /usr/src/app

# Install dependencies first using package manifests
COPY package.json package-lock.json* ./
RUN npm ci --silent || npm install --silent

# Copy source
COPY . .

EXPOSE 3000

ENV PORT=3000

CMD ["npm", "run", "dev"]
