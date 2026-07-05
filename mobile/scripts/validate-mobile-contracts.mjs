import { readFileSync } from "node:fs";
import { join } from "node:path";

const root = new URL("..", import.meta.url).pathname;

function read(path) {
  return readFileSync(join(root, path), "utf8");
}

const packageJson = JSON.parse(read("package.json"));
const appJson = JSON.parse(read("app.json"));
const routeSource = read("src/navigation/routes.ts");
const configSource = read("src/config/mobileConfig.ts");

const requiredDeps = [
  "expo",
  "expo-router",
  "aws-amplify",
  "@aws-amplify/react-native",
  "@tanstack/react-query",
  "expo-notifications",
  "expo-secure-store",
  "expo-sqlite"
];

for (const dep of requiredDeps) {
  if (!packageJson.dependencies[dep]) {
    throw new Error(`Missing dependency: ${dep}`);
  }
}

if (appJson.expo.scheme !== "stoa") {
  throw new Error("Expected stoa deep-link scheme");
}

for (const routeGroup of ["AUTH_ROUTES", "STUDENT_ROUTES", "PARENT_ROUTES", "NOTIFICATION_ROUTES", "BLOCKED_ROUTES"]) {
  if (!routeSource.includes(routeGroup)) {
    throw new Error(`Missing route group: ${routeGroup}`);
  }
}

for (const envName of [
  "EXPO_PUBLIC_STOA_API_BASE_URL",
  "EXPO_PUBLIC_STOA_COGNITO_REGION",
  "EXPO_PUBLIC_STOA_COGNITO_USER_POOL_ID",
  "EXPO_PUBLIC_STOA_COGNITO_CLIENT_ID",
  "EXPO_PUBLIC_STOA_EXPO_PROJECT_ID",
  "EXPO_PUBLIC_STOA_NO_DEMO_FALLBACK"
]) {
  if (!configSource.includes(envName)) {
    throw new Error(`Missing config env: ${envName}`);
  }
}

console.log("mobile contract checks passed");
