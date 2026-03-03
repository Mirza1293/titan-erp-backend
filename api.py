"""
TITAN ERP - FastAPI Backend
Render.com'a deploy edilecek, Supabase PostgreSQL'e bağlanacak.
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
import psycopg2
import psycopg2.extras
import os
import jwt
import datetime

# ─────────────────────────────────────────
#  AYARLAR (Render'da Environment Variable olarak girilecek)
# ─────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")       # Supabase bağlantı string'i
SECRET_KEY   = os.environ.get("SECRET_KEY", "titan_gizli_anahtar_2024")
SIFRE        = os.environ.get("APP_SIFRE", "123456")    # Giriş şifresi

app = FastAPI(title="TITAN ERP API", version="1.0.0")
security = HTTPBearer()

# CORS — masaüstü PyQt6 ve mobil PWA erişebilsin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────
#  VERİTABANI BAĞLANTISI
# ─────────────────────────────────────────
def db_baglan():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Veritabanı bağlantı hatası: {e}")

def tablolari_olustur():
    """Uygulama başlarken tabloları oluşturur."""
    conn = db_baglan()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS urunler (
            id SERIAL PRIMARY KEY,
            barkod TEXT UNIQUE,
            kategori TEXT,
            gelis_tarihi TEXT,
            kullanim_tarihi TEXT DEFAULT '-',
            tekrar_kullanim_tarihi TEXT DEFAULT '-',
            ilk_miktar REAL DEFAULT 0.0,
            kalan_miktar REAL DEFAULT 0.0,
            tekrar_miktar REAL DEFAULT 0.0
        )
    """)
    conn.commit()
    conn.close()

# Uygulama başlangıcında tabloları oluştur
try:
    tablolari_olustur()
except:
    pass  # İlk deploy'da DATABASE_URL henüz set edilmemiş olabilir

# ─────────────────────────────────────────
#  KİMLİK DOĞRULAMA (JWT)
# ─────────────────────────────────────────
def token_dogrula(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token süresi dolmuş. Tekrar giriş yapın.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Geçersiz token.")

# ─────────────────────────────────────────
#  MODEL TANIMLARI
# ─────────────────────────────────────────
class GirisIstegi(BaseModel):
    sifre: str

class UrunEkle(BaseModel):
    barkod: str
    kategori: str  # "Et" veya "Tavuk"
    gelis_tarihi: str
    kullanim_tarihi: Optional[str] = "-"
    tekrar_kullanim_tarihi: Optional[str] = "-"
    ilk_miktar: float
    kalan_miktar: float

class UrunGuncelle(BaseModel):
    barkod: Optional[str] = None
    gelis_tarihi: Optional[str] = None
    kullanim_tarihi: Optional[str] = None
    tekrar_kullanim_tarihi: Optional[str] = None
    kalan_miktar: Optional[float] = None
    tekrar_miktar: Optional[float] = None

# ─────────────────────────────────────────
#  ENDPOINT'LER
# ─────────────────────────────────────────

@app.get("/")
def root():
    return {"durum": "TITAN ERP API çalışıyor 🚀"}

# --- GİRİŞ ---
@app.post("/api/giris")
def giris_yap(istek: GirisIstegi):
    """Şifre doğruysa JWT token döner."""
    if istek.sifre != SIFRE:
        raise HTTPException(status_code=401, detail="Hatalı şifre!")
    
    payload = {
        "kullanici": "titan_kullanici",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=30)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return {"token": token, "mesaj": "Giriş başarılı!"}

# --- TÜM ÜRÜNLERİ LİSTELE ---
@app.get("/api/urunler")
def urunleri_listele(
    kategori: Optional[str] = None,
    _: dict = Depends(token_dogrula)
):
    """Tüm ürünleri getirir. kategori parametresiyle 'Et' veya 'Tavuk' filtrelenebilir."""
    conn = db_baglan()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    if kategori:
        cursor.execute(
            "SELECT * FROM urunler WHERE kategori = %s ORDER BY id DESC",
            (kategori,)
        )
    else:
        cursor.execute("SELECT * FROM urunler ORDER BY id DESC")
    
    veriler = cursor.fetchall()
    conn.close()
    return {"urunler": [dict(v) for v in veriler]}

# --- YENİ ÜRÜN EKLE ---
@app.post("/api/urunler", status_code=201)
def urun_ekle(urun: UrunEkle, _: dict = Depends(token_dogrula)):
    conn = db_baglan()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO urunler 
            (barkod, kategori, gelis_tarihi, kullanim_tarihi, tekrar_kullanim_tarihi, ilk_miktar, kalan_miktar)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            urun.barkod, urun.kategori, urun.gelis_tarihi,
            urun.kullanim_tarihi, urun.tekrar_kullanim_tarihi,
            urun.ilk_miktar, urun.kalan_miktar
        ))
        yeni_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        return {"mesaj": "Ürün eklendi.", "id": yeni_id}
    except psycopg2.errors.UniqueViolation:
        conn.close()
        raise HTTPException(status_code=409, detail="Bu barkod zaten kayıtlı!")

# --- ÜRÜN GÜNCELLE ---
@app.put("/api/urunler/{urun_id}")
def urun_guncelle(urun_id: int, guncelleme: UrunGuncelle, _: dict = Depends(token_dogrula)):
    conn = db_baglan()
    cursor = conn.cursor()

    alanlar = []
    degerler = []

    if guncelleme.barkod is not None:
        alanlar.append("barkod = %s"); degerler.append(guncelleme.barkod)
    if guncelleme.gelis_tarihi is not None:
        alanlar.append("gelis_tarihi = %s"); degerler.append(guncelleme.gelis_tarihi)
    if guncelleme.kullanim_tarihi is not None:
        alanlar.append("kullanim_tarihi = %s"); degerler.append(guncelleme.kullanim_tarihi)
    if guncelleme.tekrar_kullanim_tarihi is not None:
        alanlar.append("tekrar_kullanim_tarihi = %s"); degerler.append(guncelleme.tekrar_kullanim_tarihi)
    if guncelleme.kalan_miktar is not None:
        alanlar.append("kalan_miktar = %s"); degerler.append(guncelleme.kalan_miktar)
    if guncelleme.tekrar_miktar is not None:
        # Tekrar miktar değişince kalan miktarı da güncelle
        cursor.execute("SELECT kalan_miktar FROM urunler WHERE id = %s", (urun_id,))
        row = cursor.fetchone()
        if row:
            yeni_kalan = max(0.0, row[0] - guncelleme.tekrar_miktar)
            alanlar.append("tekrar_miktar = %s"); degerler.append(guncelleme.tekrar_miktar)
            alanlar.append("kalan_miktar = %s"); degerler.append(yeni_kalan)

    if not alanlar:
        raise HTTPException(status_code=400, detail="Güncellenecek alan bulunamadı.")

    degerler.append(urun_id)
    sorgu = f"UPDATE urunler SET {', '.join(alanlar)} WHERE id = %s"
    
    try:
        cursor.execute(sorgu, degerler)
        conn.commit()
        conn.close()
        return {"mesaj": "Güncellendi."}
    except psycopg2.errors.UniqueViolation:
        conn.close()
        raise HTTPException(status_code=409, detail="Bu barkod zaten kayıtlı!")

# --- ÜRÜN SİL ---
@app.delete("/api/urunler/{urun_id}")
def urun_sil(urun_id: int, _: dict = Depends(token_dogrula)):
    conn = db_baglan()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM urunler WHERE id = %s", (urun_id,))
    conn.commit()
    conn.close()
    return {"mesaj": "Silindi."}

# --- ANALİZ VERİSİ ---
@app.get("/api/analiz")
def analiz_getir(_: dict = Depends(token_dogrula)):
    """Dashboard için özet stok verisi."""
    conn = db_baglan()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT 
            kategori,
            SUM(ilk_miktar) as toplam_giren,
            SUM(kalan_miktar) as toplam_kalan
        FROM urunler
        GROUP BY kategori
    """)
    stok = {r["kategori"]: dict(r) for r in cursor.fetchall()}

    # Son 7 gün tüketimi
    cursor.execute("""
        SELECT kategori, SUM(ilk_miktar - kalan_miktar) as tuketilen
        FROM urunler
        WHERE kullanim_tarihi != '-'
          AND TO_DATE(kullanim_tarihi, 'DD.MM.YYYY') >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY kategori
    """)
    son_7 = {r["kategori"]: r["tuketilen"] for r in cursor.fetchall()}

    # Son 30 gün tüketimi
    cursor.execute("""
        SELECT kategori, SUM(ilk_miktar - kalan_miktar) as tuketilen
        FROM urunler
        WHERE kullanim_tarihi != '-'
          AND TO_DATE(kullanim_tarihi, 'DD.MM.YYYY') >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY kategori
    """)
    son_30 = {r["kategori"]: r["tuketilen"] for r in cursor.fetchall()}

    conn.close()
    return {
        "stok": stok,
        "son_7_gun": son_7,
        "son_30_gun": son_30
    }
