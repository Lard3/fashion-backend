import os
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from rembg import remove
from PIL import Image
import io
import requests
from openai import OpenAI
from supabase import create_client, Client

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Credenciales automáticas desde las variables de entorno de Railway
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
client_openai = OpenAI(api_key=OPENAI_API_KEY)

@app.get("/")
def read_root():
    return {"status": "Backend de moda IA activo y funcionando correctamente"}

@app.post("/process-garment")
async def process_garment(user_id: str = Form(...), file: UploadFile = File(...)):
    try:
        # 1. Leer la imagen subida desde FlutterFlow
        input_image_bytes = await file.read()
        
        # 2. Quitar el fondo con rembg
        output_image_bytes = remove(input_image_bytes)
        
        # 3. Subir la imagen limpia a Supabase Storage (bucket: wardrobe-images)
        file_name = f"{user_id}/{file.filename.split('.')[0]}_clean.png"
        supabase.storage.from_("wardrobe-images").upload(
            file_name,
            output_image_bytes,
            file_options={"content-type": "image/png", "upsert": "true"}
        )
        
        # Obtener la URL pública de la imagen en Supabase
        image_url = supabase.storage.from_("wardrobe-images").get_public_url(file_name)
        
        # 4. Enviar la imagen a OpenAI (GPT-4o mini) para etiquetar color, categoría y estilo
        response = client_openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Eres un experto en moda. Analiza la imagen de la prenda y responde estrictamente en formato JSON con estas tres claves: 'category' (ej: pantalón, top, chaqueta, calzado), 'color' (ej: azul, negro, beige), y 'style' (ej: casual, formal, streetwear)."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Clasifica esta prenda."},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ],
            response_format={"type": "json_object"}
        )
        
        import json
        ai_data = json.loads(response.choices[0].message.content)
        
        # 5. Guardar el registro en la tabla 'wardrobe_items' de Supabase
        insert_data = {
            "user_id": user_id,
            "image_url": image_url,
            "category": ai_data.get("category", "general"),
            "color": ai_data.get("color", "neutro"),
            "style": ai_data.get("style", "casual")
        }
        
        db_response = supabase.table("wardrobe_items").insert(insert_data).execute()
        
        return {
            "success": True,
            "message": "Prenda procesada con éxito",
            "data": db_response.data[0] if db_response.data else insert_data
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-looks")
async def generate_looks(garment_id: str = Form(...)):
    # Lógica base para buscar coincidencias en el catálogo de afiliados
    try:
        # Buscamos la prenda del usuario
        item_res = supabase.table("wardrobe_items").select("*").eq("id", garment_id).execute()
        if not item_res.data:
            raise HTTPException(status_code=404, detail="Prenda no encontrada")
        
        user_item = item_res.data[0]
        
        # Buscamos en el catálogo de afiliados prendas del mismo estilo
        catalog_res = supabase.table("affiliate_catalog").select("*").eq("style", user_item["style"]).limit(3).execute()
        
        return {
            "success": True,
            "base_item": user_item,
            "recommended_looks": catalog_res.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
  if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080)
