import * as SQLite from "expo-sqlite";
import { getCachePolicy, type CacheSurface } from "./cachePolicy";

export type CachedRead<T> = {
  surface: CacheSurface;
  value: T;
  cachedAt: string;
  expiresAt: string;
  stale: boolean;
};

const databaseName = "stoa-mobile-read-through-cache.db";

export const openReadThroughCache = () => SQLite.openDatabaseAsync(databaseName);

export const createCachedRead = <T>(
  surface: CacheSurface,
  value: T,
  now = new Date()
): CachedRead<T> => {
  const policy = getCachePolicy(surface);
  const expiresAt = new Date(now.getTime() + policy.ttlSeconds * 1000);

  return {
    surface,
    value,
    cachedAt: now.toISOString(),
    expiresAt: expiresAt.toISOString(),
    stale: false
  };
};

export const markCachedReadStale = <T>(cachedRead: CachedRead<T>, now = new Date()): CachedRead<T> => ({
  ...cachedRead,
  stale: new Date(cachedRead.expiresAt).getTime() <= now.getTime()
});

export const clearReadThroughCache = async (): Promise<void> => {
  const database = await openReadThroughCache();
  await database.execAsync("DELETE FROM read_through_cache");
};
