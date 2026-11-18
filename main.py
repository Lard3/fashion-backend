import io
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from rembg import remove
import os
from supabase import create_client, Client
from openai import OpenAI

# Inicializar FastAPI
app = FastAPI(title="Fashion AI Backend", version="1.0.0")

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cargar variables de entorno
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Inicializar clientes externos de forma segura
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

@app.get("/")
def root():
    return {"status": "Backend de moda IA activo y funcionando correctamente"}

@app.post("/process-garment")
async def process_garment(user_id: str = Form(...), file: UploadFile = File(...)):
    try:
        # 1. Leer los bytes de la imagen subida
        input_image_bytes = await file.read()
        
        # 2. Abrir con Pillow y redimensionar para ahorrar memoria RAM y evitar 502
        image = Image.open(io.BytesIO(input_image_bytes))
        image.thumbnail((800, 800))
        
        img_byte_arr = io.BytesIO()
        img_format = image.format if image.format and image.format in ["JPEG", "PNG"] else "JPEG"
        image.save(img_byte_arr, format=img_format)
        input_image_bytes = img_byte_arr.getvalue()
        
        # 3. Quitar el fondo con rembg de forma optimizada
        output_image_bytes = remove(input_image_bytes)
        
        # 4. Subir la imagen procesada a Supabase Storage (Bucket: wardrobe-images)
        file_name = f"{user_id}/{os.urandom(8).hex()}.png"
        image_url = None
        
        if supabase:
            try:
                supabase.storage.from_("wardrobe-images").upload(
                    file_name,
                    output_image_bytes,
                    file_options={"content-type": "image/png"}
                )
                image_url = supabase.storage.from_("wardrobe-images").get_public_url(file_name)
            except Exception as storage_err:
                print(f"Error detallado en Supabase Storage: {storage_err}")
                raise HTTPException(status_code=500, detail=f"Error en Supabase: {str(storage_err)}")
        else:
            image_url = "mock_supabase_url"

        garment_info = {
            "category": "Desconocido",
            "color": "Desconocido",
            "style": "Casual"
        }

        return {
            "success": True,
            "user_id": user_id,
            "image_url": image_url,
            "garment_info": garment_info
        }

    except Exception as e:
        print(f"Error procesando la prenda: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-looks")
async def generate_looks(user_id: str = Form(...)):
    return {
        "success": True,
        "message": "Generador de looks listo",
        "looks": []
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.main(["main:app", "--host", "0.0.0.0", "--port", str(port)])
