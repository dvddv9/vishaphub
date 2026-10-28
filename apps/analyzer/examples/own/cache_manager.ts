import Redis from "ioredis";

const redis = new Redis();

export class CacheManager {
  // BUG 1: no TTL — memory leak in Redis
  async set(key: string, value: any): Promise<void> {
    await redis.set(key, JSON.stringify(value));
  }

  // BUG 2: cache stampede — no lock, parallel misses hit origin
  async getOrLoad(key: string, loader: () => Promise<any>): Promise<any> {
    const cached = await redis.get(key);
    if (cached) {
      return JSON.parse(cached);
    }
    const value = await loader();
    await this.set(key, value);
    return value;
  }

  // BUG 3: no error handling — Redis down = app down
  async get(key: string): Promise<any> {
    const val = await redis.get(key);
    return JSON.parse(val);
  }

  // BUG 4: unbounded key scan
  async invalidateAll(): Promise<void> {
    const keys = await redis.keys("*");
    for (const k of keys) {
      await redis.del(k);
    }
  }
}
