// ═══════════════════════════════════════════════════════════════
// ByteToBite — Agro facade (v4, offline mode + auto-seed)
// MODE = 'indexeddb' — no backend required. Perfect for SIH demo.
// Change MODE to 'api' when the FastAPI server is running.
// ═══════════════════════════════════════════════════════════════

(function () {
    const isFile = typeof window !== 'undefined' && window.location.protocol === 'file:';
    const isLocal = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

    const MODE = window.BYTETOBITE_MODE || (localStorage.getItem('bytetobite:mode') || (isFile ? 'indexeddb' : 'auto'));
    const API_BASE = window.BYTETOBITE_API || (
        (isLocal || isFile)
            ? 'http://localhost:8000'
            : (localStorage.getItem('bytetobite:api_base') || 'https://bytetobite-api.onrender.com')
    );
    const WS_BASE = window.BYTETOBITE_WS || (
        API_BASE.replace(/^http/, 'ws')
    );

    async function apiOr(apiFn, localFn) {
        if (MODE === 'api' || MODE === 'auto') {
            try {
                const res = await apiFn();
                if (res !== undefined && res !== null) return res;
            } catch (err) {
                console.warn('[ByteToBite Agro] API unavailable, using local DB:', err.message);
                return await localFn();
            }
        }
        return await localFn();
    }

    const DB_NAME = 'bytetobite_agro';
    const DB_VERSION = 3;
    const STORES = {
        listings: 'listings', buyers: 'buyers', profiles: 'profiles',
        escrow: 'escrow', barter: 'barter', products: 'products',
        store_users: 'store_users', orders: 'store_orders', cart: 'cart',
        wishlist: 'wishlist', payments: 'payments',
    };

    let dbPromise = null;
    let ws = null;
    const wsSubscribers = new Set();
    let wsReconnectTimer = null;
    let seedCheckPromise = null;

    // ─────────────────────────────────────────────
    // SEED PRODUCTS — shown in Eco-Store (page6.html)
    // ─────────────────────────────────────────────
    const SEED_PRODUCTS = [
        {
            id: 'PRD-seed-001',
            title: 'Mycelium vegan leather tote bag — handcrafted',
            category: 'Paddy Straw',
            price: 4299, mrp: 6499, stock_quantity: 42,
            bestseller: true, rating: 4.9, reviews: 184,
            carbon_saved_kgco2e: 18.4,
            raw_waste_listing_code: 'w-paddy-8820',
            raw_biomass_used_kg: 24,
            description: 'High-tensile waterproof tote grown from pure fungal mycelium on upcycled paddy stubble.',
            image_url: 'https://images.unsplash.com/photo-1544816155-12df9643f363?auto=format&fit=crop&w=700&q=80',
            seller_id: 'seller-bio-craft',
            seller_name: 'BioCraft Collective, Varanasi',
            seller_verified: true,
            source_mandi: 'Tanda Mandi Hub (FPO Cluster)',
            origin_label: 'Tanda FPO, Ambedkarnagar, UP',
            origin_lat: 26.5614, origin_lng: 82.6521,
            artisan_name: 'BioCraft Collective, Varanasi',
            artisan_lat: 25.3176, artisan_lng: 82.9739,
            created_at: Date.now() - 100000,
        },
        {
            id: 'PRD-seed-002',
            title: 'Citrus bio-pectin industrial film roll (30 m)',
            category: 'Citrus Pomace',
            price: 1850, mrp: 2799, stock_quantity: 8,
            bestseller: false, rating: 4.7, reviews: 68,
            carbon_saved_kgco2e: 9.8,
            raw_waste_listing_code: 'w-pomace-4112',
            raw_biomass_used_kg: 35,
            description: 'Clear heat-sealable biodegradable food packaging film made from kinnow juice waste.',
            image_url: 'https://images.unsplash.com/photo-1528458909336-e7a0adfed0a5?auto=format&fit=crop&w=700&q=80',
            seller_id: 'seller-agripact',
            seller_name: 'AgriPact Green Polymers, Ludhiana',
            seller_verified: true,
            source_mandi: 'Abohar Citrus Mandi Cluster',
            origin_label: 'Abohar Mandi Yard #4, Fazilka, Punjab',
            origin_lat: 30.1453, origin_lng: 74.1993,
            artisan_name: 'AgriPact Green Polymers, Ludhiana',
            artisan_lat: 30.9010, artisan_lng: 75.8573,
            created_at: Date.now() - 90000,
        },
        {
            id: 'PRD-seed-003',
            title: 'Vitrified rice-husk-ash ceramic urn — handmade',
            category: 'Rice Husk',
            price: 2490, mrp: 3899, stock_quantity: 3,
            bestseller: true, rating: 4.8, reviews: 212,
            carbon_saved_kgco2e: 14.1,
            raw_waste_listing_code: 'w-husk-9034',
            raw_biomass_used_kg: 19.5,
            description: 'Dense vitrified stoneware made by blending rice-husk ash with Gangetic alluvium silt.',
            image_url: 'https://images.unsplash.com/photo-1578749556568-bc2c40e68b61?auto=format&fit=crop&w=700&q=80',
            seller_id: 'seller-terracotta',
            seller_name: 'Terracotta Guild, Gorakhpur',
            seller_verified: true,
            source_mandi: 'Bhadohi Rice Processing Mandi',
            origin_label: 'Vindhya Agro Mill, Bhadohi, UP',
            origin_lat: 25.4216, origin_lng: 82.5684,
            artisan_name: 'Terracotta Guild, Gorakhpur',
            artisan_lat: 26.7606, artisan_lng: 83.3732,
            created_at: Date.now() - 80000,
        },
        {
            id: 'PRD-seed-004',
            title: 'Banana pseudostem eco-fiber laptop sleeve',
            category: 'Banana Stalk',
            price: 1199, mrp: 1899, stock_quantity: 65,
            bestseller: false, rating: 4.6, reviews: 94,
            carbon_saved_kgco2e: 7.9,
            raw_waste_listing_code: 'w-banana-2091',
            raw_biomass_used_kg: 16,
            description: 'Hand-braided shock-absorbent laptop cover from extracted banana plant trunk fibers.',
            image_url: 'https://images.unsplash.com/photo-1606744824163-985d376605aa?auto=format&fit=crop&w=700&q=80',
            seller_id: 'seller-vrindavan',
            seller_name: 'Vrindavan AgriWeavers, Surat',
            seller_verified: false,
            source_mandi: 'Navsari Banana Plantation FPO',
            origin_label: 'Mahuva Agro Cluster, Surat, Gujarat',
            origin_lat: 20.9467, origin_lng: 72.9520,
            artisan_name: 'Vrindavan AgriWeavers, Surat',
            artisan_lat: 21.1702, artisan_lng: 72.8311,
            created_at: Date.now() - 70000,
        },
        {
            id: 'PRD-seed-005',
            title: 'Sugarcane bagasse tableware set — 6 plates',
            category: 'Plant Fiber',
            price: 899, mrp: 1499, stock_quantity: 120,
            bestseller: true, rating: 4.9, reviews: 341,
            carbon_saved_kgco2e: 6.2,
            raw_waste_listing_code: 'w-bagasse-1120',
            raw_biomass_used_kg: 12,
            description: 'Microwave-safe compostable plates pressed from sugarcane bagasse fiber.',
            image_url: 'https://images.unsplash.com/photo-1584346133934-a3afd2a33c4c?auto=format&fit=crop&w=700&q=80',
            seller_id: 'seller-bio-craft',
            seller_name: 'BioCraft Collective, Varanasi',
            seller_verified: true,
            source_mandi: 'Muzaffarnagar Sugar Mill Cluster',
            origin_label: 'Muzaffarnagar, UP',
            origin_lat: 29.4727, origin_lng: 77.7085,
            artisan_name: 'BioCraft Collective, Varanasi',
            artisan_lat: 25.3176, artisan_lng: 82.9739,
            created_at: Date.now() - 60000,
        },
        {
            id: 'PRD-seed-006',
            title: 'Spent mushroom substrate potting mix — 5 kg',
            category: 'Mushroom Substrate',
            price: 349, mrp: 599, stock_quantity: 200,
            bestseller: false, rating: 4.5, reviews: 87,
            carbon_saved_kgco2e: 4.5,
            raw_waste_listing_code: 'w-mush-0721',
            raw_biomass_used_kg: 8,
            description: 'Nutrient-rich potting mix from spent oyster mushroom substrate. Ready to use.',
            image_url: 'https://images.unsplash.com/photo-1416879595882-3373a0480b5b?auto=format&fit=crop&w=700&q=80',
            seller_id: 'seller-bio-craft',
            seller_name: 'BioCraft Collective, Varanasi',
            seller_verified: true,
            source_mandi: 'Sonbhadra Mushroom FPO',
            origin_label: 'Sonbhadra, UP',
            origin_lat: 24.6868, origin_lng: 83.0696,
            artisan_name: 'BioCraft Collective, Varanasi',
            artisan_lat: 25.3176, artisan_lng: 82.9739,
            created_at: Date.now() - 50000,
        },
    ];

    // ─────────────────────────────────────────────
    // INDEXEDDB
    // ─────────────────────────────────────────────
    function open() {
        if (dbPromise) return dbPromise;
        dbPromise = new Promise((resolve, reject) => {
            const req = indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = (e) => {
                const db = e.target.result;
                const ensure = (name, key, idx = []) => {
                    if (!db.objectStoreNames.contains(name)) {
                        const s = db.createObjectStore(name, { keyPath: key });
                        idx.forEach(([n, p, o]) => s.createIndex(n, p, o || {}));
                    }
                };
                ensure(STORES.listings, 'id', [['lot_code', 'lot_code'], ['category', 'category'], ['status', 'status'], ['created_at', 'created_at']]);
                ensure(STORES.buyers, 'id', [['role', 'role'], ['verified', 'verified'], ['city', 'city']]);
                ensure(STORES.profiles, 'id', [['role', 'role']]);
                ensure(STORES.escrow, 'id', [['listing_code', 'listing_code'], ['milestone', 'milestone'], ['created_at', 'created_at']]);
                ensure(STORES.barter, 'id', [['category', 'category'], ['created_at', 'created_at']]);
                ensure(STORES.products, 'id', [['seller_id', 'seller_id'], ['category', 'category'], ['created_at', 'created_at']]);
                ensure(STORES.store_users, 'id', [['role', 'role']]);
                ensure(STORES.orders, 'id', [['product_id', 'product_id'], ['seller_id', 'seller_id'], ['customer_id', 'customer_id'], ['status', 'status'], ['created_at', 'created_at']]);
                ensure(STORES.cart, 'id', [['user_id', 'user_id']]);
                ensure(STORES.wishlist, 'id', [['user_id', 'user_id']]);
                ensure(STORES.payments, 'id', [['listing_code', 'listing_code'], ['buyer_id', 'buyer_id'], ['status', 'status'], ['created_at', 'created_at']]);
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
        return dbPromise;
    }
    const reqToPromise = (req) => new Promise((res, rej) => { req.onsuccess = () => res(req.result); req.onerror = () => rej(req.error); });
    async function tx(store, mode, fn) {
        const db = await open();
        return new Promise((res, rej) => {
            if (!db.objectStoreNames.contains(store)) return rej(new Error('Store not found: ' + store));
            const t = db.transaction(store, mode);
            const s = t.objectStore(store);
            let r; try { r = fn(s); } catch (e) { return rej(e); }
            t.oncomplete = () => res(r); t.onerror = () => rej(t.error); t.onabort = () => rej(t.error);
        });
    }
    const ping = () => { try { localStorage.setItem('bytetobite:ping', Date.now().toString()); } catch { } };
    const broadcast = (n) => { window.dispatchEvent(new CustomEvent(n)); ping(); };
    const newId = (p) => p + '-' + Date.now().toString(36).toUpperCase() + '-' + Math.floor(Math.random() * 9999);
    const authHeader = () => { try { const r = localStorage.getItem('bytetobite:jwt'); return r ? { Authorization: `Bearer ${r}` } : {}; } catch { return {}; } };

    async function http(path, { method = 'GET', body, headers = {} } = {}) {
        const res = await fetch(`${API_BASE}${path}`, {
            method,
            headers: { 'Content-Type': 'application/json', ...authHeader(), ...headers },
            body: body != null ? JSON.stringify(body) : undefined,
        });
        if (!res.ok) { let d = res.statusText; try { const j = await res.json(); d = j.detail || d; } catch { } throw new Error(`${res.status} ${d}`); }
        if (res.status === 204) return null;
        return res.json();
    }

    function haversineKm(lat1, lng1, lat2, lng2) {
        const R = 6371;
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLng = (lng2 - lng1) * Math.PI / 180;
        const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    // ─────────────────────────────────────────────
    // SEED THE ECO-STORE ONCE
    // Called automatically the first time getProducts runs.
    // ─────────────────────────────────────────────
    async function ensureSeeded() {
        if (MODE === 'api') return;
        if (seedCheckPromise) return seedCheckPromise;
        seedCheckPromise = (async () => {
            try {
                const db = await open();
                const t = db.transaction(STORES.products, 'readonly');
                const existing = await reqToPromise(t.objectStore(STORES.products).getAll());
                if (existing && existing.length > 0) return;   // already seeded
                const w = db.transaction(STORES.products, 'readwrite');
                const s = w.objectStore(STORES.products);
                for (const p of SEED_PRODUCTS) s.put(p);
                await new Promise((res, rej) => {
                    w.oncomplete = () => res();
                    w.onerror = () => rej(w.error);
                    w.onabort = () => rej(w.error);
                });
                broadcast('bytetobite:products-changed');
                console.log('[ByteToBite] Eco-Store seeded with', SEED_PRODUCTS.length, 'demo products.');
            } catch (e) {
                console.warn('[ByteToBite] Eco-Store seed failed:', e);
            }
        })();
        return seedCheckPromise;
    }

    // ─────────────────────────────────────────────
    // FACADE
    // ─────────────────────────────────────────────
    const api = {
        MODE,

        // ── LISTINGS ───────────────────────────────────────────
        async publishLot(lot) {
            return apiOr(
                async () => {
                    const saved = await http('/api/listings', { method: 'POST', body: lot });
                    try { const db = await open(); await tx(STORES.listings, 'readwrite', s => s.put(saved)); } catch {}
                    broadcast('bytetobite:listings-changed');
                    return saved;
                },
                async () => {
                    lot.id = lot.id || newId('LOT');
                    lot.lot_code = lot.lot_code || ('LOT-' + Date.now().toString().slice(-6));
                    lot.created_at = lot.created_at || Date.now();
                    lot.updated_at = Date.now();
                    lot.status = lot.status || 'OPEN';
                    await tx(STORES.listings, 'readwrite', s => s.put(lot));
                    broadcast('bytetobite:listings-changed');
                    return lot;
                }
            );
        },
        async getLots() {
            return apiOr(
                () => http('/api/listings'),
                async () => {
                    const db = await open(); const t = db.transaction(STORES.listings, 'readonly');
                    const all = await reqToPromise(t.objectStore(STORES.listings).getAll());
                    return all.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
                }
            );
        },
        async getLot(id) {
            return apiOr(
                () => http(`/api/listings/${encodeURIComponent(id)}`),
                async () => {
                    const db = await open(); const t = db.transaction(STORES.listings, 'readonly');
                    return reqToPromise(t.objectStore(STORES.listings).get(id));
                }
            );
        },
        async deleteLot(id) {
            return apiOr(
                async () => {
                    await http(`/api/listings/${id}`, { method: 'DELETE' });
                    try { const db = await open(); await tx(STORES.listings, 'readwrite', s => s.delete(id)); } catch {}
                    broadcast('bytetobite:listings-changed');
                },
                async () => {
                    await tx(STORES.listings, 'readwrite', s => s.delete(id));
                    broadcast('bytetobite:listings-changed');
                }
            );
        },
        async matchBuyers(lot, radiusKm = 50) {
            if (MODE === 'api') return http(`/api/listings/${encodeURIComponent(lot.id || lot.lot_code)}/matches?radius=${radiusKm}`);
            const buyers = await api.getAllBuyers();
            const lotLoc = lot.location || { lat: lot.lat, lng: lot.lng };
            return buyers.filter(b => b.verified !== false && b.location)
                .filter(b => !b.accepted_categories?.length || b.accepted_categories.includes(lot.category))
                .map(b => ({ ...b, distance_km: haversineKm(lotLoc.lat, lotLoc.lng, b.location.lat, b.location.lng) }))
                .filter(b => b.distance_km <= radiusKm)
                .sort((a, b) => a.distance_km - b.distance_km).slice(0, 20);
        },

        // ── BUYERS ─────────────────────────────────────────────
        async registerBuyer(buyer) {
            if (MODE === 'api') { const s = await http('/api/buyers', { method: 'POST', body: buyer }); broadcast('bytetobite:buyers-changed'); return s; }
            buyer.id = buyer.id || newId('BUY');
            buyer.created_at = buyer.created_at || Date.now();
            await tx(STORES.buyers, 'readwrite', s => s.put(buyer));
            broadcast('bytetobite:buyers-changed');
            return buyer;
        },
        async getAllBuyers() {
            if (MODE === 'api') return http('/api/buyers');
            const db = await open(); const t = db.transaction(STORES.buyers, 'readonly');
            return reqToPromise(t.objectStore(STORES.buyers).getAll());
        },
        async getBuyersByRole(role) {
            if (MODE === 'api') return http(`/api/buyers?role=${encodeURIComponent(role)}`);
            const db = await open(); const t = db.transaction(STORES.buyers, 'readonly');
            return reqToPromise(t.objectStore(STORES.buyers).index('role').getAll(role));
        },

        // ── PROFILES ───────────────────────────────────────────
        async saveProfile(role, profile) {
            if (MODE === 'api') { const s = await http('/api/profiles', { method: 'POST', body: { role, ...profile } }); broadcast('bytetobite:profiles-changed'); return s; }
            const entry = { id: role, role, ...profile, updated_at: Date.now(), created_at: profile.created_at || Date.now() };
            await tx(STORES.profiles, 'readwrite', s => s.put(entry));
            broadcast('bytetobite:profiles-changed');
            return entry;
        },
        async getProfile(role) {
            if (MODE === 'api') { const rows = await http(`/api/profiles?role=${encodeURIComponent(role)}`); return Array.isArray(rows) ? rows[0] : rows; }
            const db = await open(); const t = db.transaction(STORES.profiles, 'readonly');
            return reqToPromise(t.objectStore(STORES.profiles).get(role));
        },
        async getAllProfiles() {
            if (MODE === 'api') return http('/api/profiles');
            const db = await open(); const t = db.transaction(STORES.profiles, 'readonly');
            return reqToPromise(t.objectStore(STORES.profiles).getAll());
        },
        async clearProfiles() {
            if (MODE === 'api') { await http('/api/profiles', { method: 'DELETE' }); broadcast('bytetobite:profiles-changed'); return; }
            await tx(STORES.profiles, 'readwrite', s => s.clear());
            broadcast('bytetobite:profiles-changed');
        },

        // ── ESCROW ─────────────────────────────────────────────
        async recordEscrow(entry) {
            if (MODE === 'api') { const s = await http('/api/escrow', { method: 'POST', body: entry }); broadcast('bytetobite:escrow-changed'); return s; }
            entry.id = entry.id || newId('ESC');
            entry.created_at = entry.created_at || Date.now();
            await tx(STORES.escrow, 'readwrite', s => s.put(entry));
            broadcast('bytetobite:escrow-changed');
            return entry;
        },
        async getEscrowForLot(listing_code) {
            if (MODE === 'api') return http(`/api/escrow?listing=${encodeURIComponent(listing_code)}`);
            const db = await open(); const t = db.transaction(STORES.escrow, 'readonly');
            return reqToPromise(t.objectStore(STORES.escrow).index('listing_code').getAll(listing_code));
        },
        async getAllEscrow() {
            if (MODE === 'api') return http('/api/escrow');
            const db = await open(); const t = db.transaction(STORES.escrow, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.escrow).getAll());
            return all.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
        },

        // ── BARTER ─────────────────────────────────────────────
        async publishBarter(barter) {
            if (MODE === 'api') { const s = await http('/api/barter', { method: 'POST', body: barter }); broadcast('bytetobite:barter-changed'); return s; }
            barter.id = barter.id || newId('BARTER');
            barter.created_at = barter.created_at || Date.now();
            await tx(STORES.barter, 'readwrite', s => s.put(barter));
            broadcast('bytetobite:barter-changed');
            return barter;
        },
        async getBarterListings() {
            if (MODE === 'api') return http('/api/barter');
            const db = await open(); const t = db.transaction(STORES.barter, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.barter).getAll());
            return all.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
        },

        // ── COMPOST ────────────────────────────────────────────
        async getDivertedLots() {
            if (MODE === 'api') return http('/api/listings?status=DIVERTED');
            return (await api.getLots()).filter(l => l.status === 'DIVERTED');
        },
        async getCompostBatches() {
            if (MODE === 'api') return http('/api/listings?category=COMPOST_FINISHED');
            return (await api.getLots()).filter(l => l.category === 'COMPOST_FINISHED');
        },

        // ── STORE PRODUCTS (Eco-Store) ─────────────────────────
        async saveProduct(product) {
            if (MODE === 'api') {
                const s = product.id
                    ? await http(`/api/store/products/${product.id}`, { method: 'PUT', body: product })
                    : await http('/api/store/products', { method: 'POST', body: product });
                broadcast('bytetobite:products-changed'); return s;
            }
            product.id = product.id || newId('PROD');
            product.created_at = product.created_at || Date.now();
            product.updated_at = Date.now();
            await tx(STORES.products, 'readwrite', s => s.put(product));
            broadcast('bytetobite:products-changed');
            return product;
        },
        async getAllProducts() {
            if (MODE === 'api') return http('/api/store/products');
            await ensureSeeded();                       // ← AUTO-SEED HERE
            const db = await open(); const t = db.transaction(STORES.products, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.products).getAll());
            return all.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
        },
        async getProduct(id) {
            if (MODE === 'api') return http(`/api/store/products/${encodeURIComponent(id)}`);
            const db = await open(); const t = db.transaction(STORES.products, 'readonly');
            return reqToPromise(t.objectStore(STORES.products).get(id));
        },
        async getProductsBySeller(seller_id) {
            if (MODE === 'api') return http(`/api/store/products?seller=${encodeURIComponent(seller_id)}`);
            const db = await open(); const t = db.transaction(STORES.products, 'readonly');
            return reqToPromise(t.objectStore(STORES.products).index('seller_id').getAll(seller_id));
        },
        async deleteProduct(id) {
            if (MODE === 'api') { await http(`/api/store/products/${id}`, { method: 'DELETE' }); broadcast('bytetobite:products-changed'); return; }
            await tx(STORES.products, 'readwrite', s => s.delete(id));
            broadcast('bytetobite:products-changed');
        },

        // ── STORE USERS ────────────────────────────────────────
        async saveStoreUser(user) {
            if (MODE === 'api') { const s = await http('/api/store/users', { method: 'POST', body: user }); broadcast('bytetobite:store-users-changed'); return s; }
            user.id = user.id || newId('USER');
            user.created_at = user.created_at || Date.now();
            await tx(STORES.store_users, 'readwrite', s => s.put(user));
            broadcast('bytetobite:store-users-changed');
            return user;
        },
        async getStoreUser(role) {
            if (MODE === 'api') { const rows = await http(`/api/store/users?role=${encodeURIComponent(role)}`); return Array.isArray(rows) ? (rows[rows.length - 1] || null) : rows; }
            const db = await open(); const t = db.transaction(STORES.store_users, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.store_users).index('role').getAll(role));
            return all[all.length - 1] || null;
        },
        async getAllStoreUsers() {
            if (MODE === 'api') return http('/api/store/users');
            const db = await open(); const t = db.transaction(STORES.store_users, 'readonly');
            return reqToPromise(t.objectStore(STORES.store_users).getAll());
        },
        async clearStoreUsers() {
            if (MODE === 'api') { await http('/api/store/users', { method: 'DELETE' }); broadcast('bytetobite:store-users-changed'); return; }
            await tx(STORES.store_users, 'readwrite', s => s.clear());
            broadcast('bytetobite:store-users-changed');
        },

        // ── STORE ORDERS ───────────────────────────────────────
        async saveStoreOrder(order) {
            if (MODE === 'api') {
                const s = await http('/api/store/orders', { method: 'POST', body: order });
                broadcast('bytetobite:orders-changed'); broadcast('bytetobite:products-changed');
                return s;
            }
            order.id = order.id || newId('ORD');
            order.order_code = order.order_code || ('ORD-' + Date.now().toString().slice(-6));
            order.created_at = order.created_at || Date.now();
            order.status = order.status || 'PLACED';
            await tx(STORES.orders, 'readwrite', s => s.put(order));
            if (order.product_id && typeof order.qty === 'number') {
                const product = await api.getProduct(order.product_id);
                if (product && product.stock_quantity != null) {
                    product.stock_quantity = Math.max(0, (product.stock_quantity || 0) - order.qty);
                    await tx(STORES.products, 'readwrite', s => s.put(product));
                }
            }
            broadcast('bytetobite:orders-changed'); broadcast('bytetobite:products-changed');
            return order;
        },
        async getStoreOrders(filter = {}) {
            if (MODE === 'api') { const q = new URLSearchParams(filter).toString(); return http('/api/store/orders' + (q ? '?' + q : '')); }
            const db = await open(); const t = db.transaction(STORES.orders, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.orders).getAll());
            let rows = all;
            if (filter.seller_id) rows = rows.filter(o => o.seller_id === filter.seller_id);
            if (filter.customer_id) rows = rows.filter(o => o.customer_id === filter.customer_id);
            if (filter.status) rows = rows.filter(o => o.status === filter.status);
            return rows.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
        },

        // ── CART ───────────────────────────────────────────────
        async saveCart(cart) {
            if (MODE === 'api') { const s = await http('/api/store/cart', { method: 'PUT', body: cart }); broadcast('bytetobite:cart-changed'); return s; }
            cart.id = cart.id || 'default-cart';
            cart.updated_at = Date.now();
            cart.created_at = cart.created_at || Date.now();
            await tx(STORES.cart, 'readwrite', s => s.put(cart));
            broadcast('bytetobite:cart-changed');
            return cart;
        },
        async getCart() {
            if (MODE === 'api') return http('/api/store/cart');
            const db = await open(); const t = db.transaction(STORES.cart, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.cart).getAll());
            return all[0] || null;
        },

        // ── WISHLIST ───────────────────────────────────────────
        async saveWishlist(userId, list) {
            if (MODE === 'api') { const s = await http('/api/store/wishlist', { method: 'PUT', body: { user_id: userId, list } }); broadcast('bytetobite:wishlist-changed'); return s; }
            const entry = { id: userId || 'default', user_id: userId, list, updated_at: Date.now() };
            entry.created_at = entry.created_at || Date.now();
            await tx(STORES.wishlist, 'readwrite', s => s.put(entry));
            broadcast('bytetobite:wishlist-changed');
            return entry;
        },
        async getWishlist(userId) {
            if (MODE === 'api') { const rows = await http(`/api/store/wishlist?user=${encodeURIComponent(userId || '')}`); return Array.isArray(rows) ? rows : (rows?.list || []); }
            const db = await open(); const t = db.transaction(STORES.wishlist, 'readonly');
            const entry = await reqToPromise(t.objectStore(STORES.wishlist).get(userId || 'default'));
            return entry ? entry.list : [];
        },

        // ── PAYMENTS ───────────────────────────────────────────
        async savePayment(payment) {
            if (MODE === 'api') { const s = await http('/api/payments', { method: 'POST', body: payment }); broadcast('bytetobite:payments-changed'); return s; }
            payment.id = payment.id || newId('PAY');
            payment.created_at = payment.created_at || Date.now();
            await tx(STORES.payments, 'readwrite', s => s.put(payment));
            broadcast('bytetobite:payments-changed');
            return payment;
        },
        async getPayments(filter = {}) {
            if (MODE === 'api') { const q = new URLSearchParams(filter).toString(); return http('/api/payments' + (q ? '?' + q : '')); }
            const db = await open(); const t = db.transaction(STORES.payments, 'readonly');
            const all = await reqToPromise(t.objectStore(STORES.payments).getAll());
            let rows = all;
            if (filter.listing_code) rows = rows.filter(p => p.listing_code === filter.listing_code);
            if (filter.buyer_id) rows = rows.filter(p => p.buyer_id === filter.buyer_id);
            if (filter.status) rows = rows.filter(p => p.status === filter.status);
            return rows.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
        },

        // ── LIVE SUBSCRIPTION ──────────────────────────────────
        subscribe(callback) {
            if (MODE === 'api') {
                wsSubscribers.add(callback); if (!ws) openWs();
                return () => wsSubscribers.delete(callback);
            }
            const events = [
                'bytetobite:listings-changed', 'bytetobite:buyers-changed', 'bytetobite:profiles-changed',
                'bytetobite:escrow-changed', 'bytetobite:barter-changed', 'bytetobite:products-changed',
                'bytetobite:store-users-changed', 'bytetobite:orders-changed', 'bytetobite:cart-changed',
                'bytetobite:wishlist-changed', 'bytetobite:payments-changed', 'storage',
            ];
            const handler = () => callback();
            events.forEach(ev => window.addEventListener(ev, handler));
            return () => events.forEach(ev => window.removeEventListener(ev, handler));
        },

        // ── MANUAL SEED (used by DevTools / Shift+D) ───────────
        async _seedDemoProducts() {
            await tx(STORES.products, 'readwrite', s => {
                for (const p of SEED_PRODUCTS) s.put(p);
            });
            broadcast('bytetobite:products-changed');
            return SEED_PRODUCTS.length;
        },
    };

    function openWs() {
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
        try { ws = new WebSocket(`${WS_BASE}/ws`); } catch { scheduleReconnect(); return; }
        ws.onmessage = (e) => {
            try {
                const p = JSON.parse(e.data); const t = p.type || '';
                if (t.endsWith('-changed')) { broadcast(`bytetobite:${t}`); wsSubscribers.forEach(cb => { try { cb(`bytetobite:${t}`); } catch { } }); }
            } catch { }
        };
        ws.onclose = scheduleReconnect;
        ws.onerror = () => { try { ws.close(); } catch { } };
    }
    function scheduleReconnect() {
        if (wsReconnectTimer) return;
        wsReconnectTimer = setTimeout(() => { wsReconnectTimer = null; if (wsSubscribers.size) openWs(); }, 3000);
    }

    window.ByteToBiteAPI = api;

    // Auto-seed as soon as the facade is available
    ensureSeeded();
})();