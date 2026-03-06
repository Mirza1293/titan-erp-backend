"""
VAŞAK ERP - FastAPI Backend v15.0 Maviş 🐱
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

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SECRET_KEY   = os.environ.get("SECRET_KEY", "vasak_gizli_anahtar_2024")
SIFRE        = os.environ.get("APP_SIFRE", "123456")

app = FastAPI(title="VAŞAK ERP API", version="15.0.0")
security = HTTPBearer()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def db_baglan():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Veritabanı bağlantı hatası: {e}")

def tablolari_olustur():
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
            tekrar_miktar REAL DEFAULT 0.0,
            kuvet_kullanim_tarihi TEXT DEFAULT '-',
            takoz_kullanim_tarihi TEXT DEFAULT '-',
            kuvet_miktar REAL DEFAULT 0.0,
            takoz_miktar REAL DEFAULT 0.0
        )
    """)
    # Mevcut tabloya yeni kolonları ekle (zaten varsa hata vermez)
    for kolon, tip in [
        ("kuvet_kullanim_tarihi", "TEXT DEFAULT '-'"),
        ("takoz_kullanim_tarihi", "TEXT DEFAULT '-'"),
        ("kuvet_miktar", "REAL DEFAULT 0.0"),
        ("takoz_miktar", "REAL DEFAULT 0.0"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE urunler ADD COLUMN IF NOT EXISTS {kolon} {tip}")
        except:
            pass
    conn.commit()
    conn.close()

try:
    tablolari_olustur()
except:
    pass

def token_dogrula(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token süresi dolmuş. Tekrar giriş yapın.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Geçersiz token.")

class GirisIstegi(BaseModel):
    sifre: str

class UrunEkle(BaseModel):
    barkod: str
    kategori: str
    gelis_tarihi: str
    kullanim_tarihi: Optional[str] = "-"
    tekrar_kullanim_tarihi: Optional[str] = "-"
    ilk_miktar: float
    kalan_miktar: float
    kuvet_kullanim_tarihi: Optional[str] = "-"
    takoz_kullanim_tarihi: Optional[str] = "-"
    kuvet_miktar: Optional[float] = 0.0
    takoz_miktar: Optional[float] = 0.0

class UrunGuncelle(BaseModel):
    barkod: Optional[str] = None
    gelis_tarihi: Optional[str] = None
    kullanim_tarihi: Optional[str] = None
    tekrar_kullanim_tarihi: Optional[str] = None
    kalan_miktar: Optional[float] = None
    tekrar_miktar: Optional[float] = None
    kuvet_kullanim_tarihi: Optional[str] = None
    takoz_kullanim_tarihi: Optional[str] = None
    kuvet_miktar: Optional[float] = None
    takoz_miktar: Optional[float] = None

@app.get("/")
def root():
    return {"durum": "VAŞAK ERP API v15.0 Maviş 🐱"}

@app.post("/api/giris")
def giris_yap(istek: GirisIstegi):
    if istek.sifre != SIFRE:
        raise HTTPException(status_code=401, detail="Hatalı şifre!")
    payload = {
        "kullanici": "vasak_kullanici",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=30)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return {"token": token, "mesaj": "Giriş başarılı!"}

@app.get("/api/urunler")
def urunleri_listele(kategori: Optional[str] = None, _: dict = Depends(token_dogrula)):
    conn = db_baglan()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if kategori:
        cursor.execute("SELECT * FROM urunler WHERE kategori = %s ORDER BY id DESC", (kategori,))
    else:
        cursor.execute("SELECT * FROM urunler ORDER BY id DESC")
    veriler = cursor.fetchall()
    conn.close()
    return {"urunler": [dict(v) for v in veriler]}

@app.post("/api/urunler", status_code=201)
def urun_ekle(urun: UrunEkle, _: dict = Depends(token_dogrula)):
    conn = db_baglan()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO urunler 
            (barkod, kategori, gelis_tarihi, kullanim_tarihi, tekrar_kullanim_tarihi,
             ilk_miktar, kalan_miktar, kuvet_kullanim_tarihi, takoz_kullanim_tarihi,
             kuvet_miktar, takoz_miktar)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            urun.barkod, urun.kategori, urun.gelis_tarihi,
            urun.kullanim_tarihi, urun.tekrar_kullanim_tarihi,
            urun.ilk_miktar, urun.kalan_miktar,
            urun.kuvet_kullanim_tarihi, urun.takoz_kullanim_tarihi,
            urun.kuvet_miktar, urun.takoz_miktar
        ))
        yeni_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        return {"mesaj": "Ürün eklendi.", "id": yeni_id}
    except psycopg2.errors.UniqueViolation:
        conn.close()
        raise HTTPException(status_code=409, detail="Bu barkod zaten kayıtlı!")

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
    if guncelleme.kuvet_kullanim_tarihi is not None:
        alanlar.append("kuvet_kullanim_tarihi = %s"); degerler.append(guncelleme.kuvet_kullanim_tarihi)
    if guncelleme.takoz_kullanim_tarihi is not None:
        alanlar.append("takoz_kullanim_tarihi = %s"); degerler.append(guncelleme.takoz_kullanim_tarihi)
    if guncelleme.kalan_miktar is not None:
        alanlar.append("kalan_miktar = %s"); degerler.append(guncelleme.kalan_miktar)

    # Küvet miktarı → kalandan düş
    if guncelleme.kuvet_miktar is not None and guncelleme.kuvet_miktar > 0:
        cursor.execute("SELECT kalan_miktar FROM urunler WHERE id = %s", (urun_id,))
        row = cursor.fetchone()
        if row:
            yeni_kalan = max(0.0, row[0] - guncelleme.kuvet_miktar)
            alanlar.append("kuvet_miktar = %s"); degerler.append(guncelleme.kuvet_miktar)
            alanlar.append("kalan_miktar = %s"); degerler.append(yeni_kalan)

    # Takoz miktarı → kalandan düş
    if guncelleme.takoz_miktar is not None and guncelleme.takoz_miktar > 0:
        cursor.execute("SELECT kalan_miktar FROM urunler WHERE id = %s", (urun_id,))
        row = cursor.fetchone()
        if row:
            yeni_kalan = max(0.0, row[0] - guncelleme.takoz_miktar)
            alanlar.append("takoz_miktar = %s"); degerler.append(guncelleme.takoz_miktar)
            alanlar.append("kalan_miktar = %s"); degerler.append(yeni_kalan)

    # Eski tekrar miktar (geriye dönük uyumluluk)
    if guncelleme.tekrar_miktar is not None:
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

@app.delete("/api/urunler/{urun_id}")
def urun_sil(urun_id: int, _: dict = Depends(token_dogrula)):
    conn = db_baglan()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM urunler WHERE id = %s", (urun_id,))
    conn.commit()
    conn.close()
    return {"mesaj": "Silindi."}

@app.get("/api/analiz")
def analiz_getir(_: dict = Depends(token_dogrula)):
    conn = db_baglan()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT kategori,
            SUM(ilk_miktar) as toplam_giren,
            SUM(kalan_miktar) as toplam_kalan
        FROM urunler GROUP BY kategori
    """)
    stok = {r["kategori"]: dict(r) for r in cursor.fetchall()}

    # Son 7 gün — küvet ve takoz tarihleri de dahil
    cursor.execute("""
        SELECT kategori, SUM(ilk_miktar - kalan_miktar) as tuketilen
        FROM urunler
        WHERE (kullanim_tarihi != '-' AND TO_DATE(kullanim_tarihi, 'DD.MM.YYYY') >= CURRENT_DATE - INTERVAL '7 days')
           OR (kuvet_kullanim_tarihi != '-' AND TO_DATE(kuvet_kullanim_tarihi, 'DD.MM.YYYY') >= CURRENT_DATE - INTERVAL '7 days')
           OR (takoz_kullanim_tarihi != '-' AND TO_DATE(takoz_kullanim_tarihi, 'DD.MM.YYYY') >= CURRENT_DATE - INTERVAL '7 days')
        GROUP BY kategori
    """)
    son_7 = {r["kategori"]: r["tuketilen"] for r in cursor.fetchall()}

    # Son 30 gün
    cursor.execute("""
        SELECT kategori, SUM(ilk_miktar - kalan_miktar) as tuketilen
        FROM urunler
        WHERE (kullanim_tarihi != '-' AND TO_DATE(kullanim_tarihi, 'DD.MM.YYYY') >= CURRENT_DATE - INTERVAL '30 days')
           OR (kuvet_kullanim_tarihi != '-' AND TO_DATE(kuvet_kullanim_tarihi, 'DD.MM.YYYY') >= CURRENT_DATE - INTERVAL '30 days')
           OR (takoz_kullanim_tarihi != '-' AND TO_DATE(takoz_kullanim_tarihi, 'DD.MM.YYYY') >= CURRENT_DATE - INTERVAL '30 days')
        GROUP BY kategori
    """)
    son_30 = {r["kategori"]: r["tuketilen"] for r in cursor.fetchall()}

    conn.close()
    return {"stok": stok, "son_7_gun": son_7, "son_30_gun": son_30}
