import streamlit as st
import os
from PIL import Image
import pandas as pd
from datetime import datetime
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

# Configuration de la page
st.set_page_config(
    page_title="Annotation Images bbox/crop",
    page_icon="🖼️",
    layout="wide"
)

# ==================== CONFIGURATION ====================

CLASSES_DISPONIBLES = ["fissure_degradee", "fissure_significative", "joint_ouvert", "faiencage"]
SAVE_FOLDER = "sauvegardes_annotations_images"
IMAGES_SUFFIXES = ["_bbox", "_crop"]

# Configuration email
SMTP_CONFIG = {
    "server": "smtp.gmail.com",
    "port": 587,
    "sender": "maamatou.houda@gmail.com",
    "password": "fziq atni xvlb ynwl",
    "receiver": "houda.maamatou@logiroad-center.com"
}

# ==================== FONCTIONS UTILITAIRES ====================

def scan_images_directory(root_dir):
    """
    Scanne le dossier racine et récupère toutes les paires d'images bbox/crop
    Retourne une liste de dictionnaires avec les informations des images
    """
    images_data = []
    
    if not os.path.exists(root_dir):
        st.error(f"❌ Le dossier '{root_dir}' n'existe pas!")
        return images_data
    
    # Parcourir tous les sous-dossiers
    for subdir in sorted(os.listdir(root_dir)):
        subdir_path = os.path.join(root_dir, subdir)
        
        if not os.path.isdir(subdir_path):
            continue
        
        # Récupérer toutes les images du sous-dossier
        image_files = [f for f in os.listdir(subdir_path) 
                      if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        
        # Grouper les images par nom de base (sans _bbox/_crop)
        image_groups = {}
        for img_file in image_files:
            # Trouver le nom de base
            base_name = img_file
            for suffix in IMAGES_SUFFIXES:
                if suffix in base_name:
                    base_name = base_name.split(suffix)[0]
                    break
            
            if base_name not in image_groups:
                image_groups[base_name] = {}
            
            # Déterminer le type (bbox ou crop)
            if "_bbox" in img_file:
                image_groups[base_name]["bbox"] = img_file
            elif "_crop" in img_file:
                image_groups[base_name]["crop"] = img_file
        
        # Créer les entrées pour les paires complètes
        for base_name, files in image_groups.items():
            if "bbox" in files and "crop" in files:
                images_data.append({
                    "base_name": base_name,
                    "folder": subdir,
                    "label_initial": subdir,
                    "bbox_file": files["bbox"],
                    "crop_file": files["crop"],
                    "bbox_path": os.path.join(subdir_path, files["bbox"]),
                    "crop_path": os.path.join(subdir_path, files["crop"])
                })
    
    return images_data

def initialize_session(images_data):
    """Initialise les réponses pour toutes les images"""
    if "responses" not in st.session_state:
        st.session_state.responses = {}
    
    for i, img_data in enumerate(images_data):
        if i not in st.session_state.responses:
            st.session_state.responses[i] = {
                "label_choisi": img_data["label_initial"],
                "commentaire": ""
            }

def get_save_filepath(annotator_name):
    """Génère le chemin du fichier de sauvegarde"""
    if not os.path.exists(SAVE_FOLDER):
        os.makedirs(SAVE_FOLDER)
    
    safe_name = "".join(c for c in annotator_name if c.isalnum() or c in (' ', '_')).strip()
    safe_name = safe_name.replace(' ', '_')
    return os.path.join(SAVE_FOLDER, f"sauvegarde_{safe_name}.json")

def save_progress(images_data):
    """Sauvegarde la progression actuelle"""
    if not st.session_state.annotator_name:
        return False, "Nom d'annotateur manquant"
    
    save_data = {
        "annotateur": st.session_state.annotator_name,
        "root_directory": st.session_state.root_directory,
        "date_sauvegarde": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "current_index": st.session_state.current_index,
        "responses": st.session_state.responses,
        "total_images": len(images_data)
    }
    
    filepath = get_save_filepath(st.session_state.annotator_name)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        return True, f"✅ Sauvegarde réussie"
    except Exception as e:
        return False, f"❌ Erreur: {str(e)}"

def load_progress(annotator_name):
    """Charge une sauvegarde existante"""
    filepath = get_save_filepath(annotator_name)
    if not os.path.exists(filepath):
        return None, "Aucune sauvegarde trouvée"
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            save_data = json.load(f)
        
        # Convertir les clés en int
        if 'responses' in save_data:
            save_data['responses'] = {
                int(k): v for k, v in save_data['responses'].items()
            }
        
        return save_data, "✅ Sauvegarde chargée"
    except Exception as e:
        return None, f"❌ Erreur: {str(e)}"

def list_saved_sessions():
    """Liste toutes les sessions sauvegardées"""
    if not os.path.exists(SAVE_FOLDER):
        return []
    
    saves = []
    for filename in os.listdir(SAVE_FOLDER):
        if filename.startswith("sauvegarde_") and filename.endswith(".json"):
            filepath = os.path.join(SAVE_FOLDER, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    saves.append({
                        'annotateur': data.get('annotateur', 'Inconnu'),
                        'date': data.get('date_sauvegarde', 'Inconnue'),
                        'progression': f"{data.get('current_index', 0)}/{data.get('total_images', 0)}",
                        'filename': filename,
                        'root_directory': data.get('root_directory', '')
                    })
            except:
                continue
    return saves

def export_to_csv(images_data):
    """Exporte les annotations au format CSV"""
    results = []
    for i, img_data in enumerate(images_data):
        response = st.session_state.responses.get(i, {})
        results.append({
            "image_bbox": img_data["bbox_file"],
            "image_crop": img_data["crop_file"],
            "dossier_source": img_data["folder"],
            "label_initial": img_data["label_initial"],
            "label_choisi": response.get("label_choisi", ""),
            "commentaire": response.get("commentaire", "")
        })
    
    df = pd.DataFrame(results)
    return df.to_csv(index=False).encode('utf-8')

def send_completion_email(annotator_name, images_data, csv_content):
    """Envoie un email de notification de fin d'annotation"""
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_CONFIG["sender"]
        msg['To'] = SMTP_CONFIG["receiver"]
        msg['Subject'] = f"✅ Annotation terminée - {annotator_name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        completed = sum(1 for r in st.session_state.responses.values() if r.get("label_choisi"))
        
        body = f"""
Bonjour,

L'annotateur {annotator_name} a terminé l'annotation des images.

📊 Statistiques:
- Total d'images: {len(images_data)}
- Images annotées: {completed}
- Date de fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Dossier source: {st.session_state.root_directory}

Les résultats détaillés sont disponibles en pièce jointe au format CSV.

Cordialement,
Système d'annotation automatique
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Ajouter le CSV en pièce jointe
        csv_attachment = MIMEBase('application', 'octet-stream')
        csv_attachment.set_payload(csv_content)
        encoders.encode_base64(csv_attachment)
        csv_attachment.add_header(
            'Content-Disposition',
            f'attachment; filename=annotations_{annotator_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
        msg.attach(csv_attachment)
        
        # Envoyer l'email
        server = smtplib.SMTP(SMTP_CONFIG["server"], SMTP_CONFIG["port"])
        server.starttls()
        server.login(SMTP_CONFIG["sender"], SMTP_CONFIG["password"])
        server.send_message(msg)
        server.quit()
        
        return True, "📧 Email envoyé avec succès!"
    
    except Exception as e:
        return False, f"❌ Erreur d'envoi email: {str(e)}"

def reset_session():
    """Réinitialise la session"""
    st.session_state.current_index = 0
    st.session_state.annotator_name = ""
    st.session_state.root_directory = ""
    st.session_state.started = False
    st.session_state.responses = {}
    st.session_state.images_data = []

# ==================== INITIALISATION ====================

if "current_index" not in st.session_state:
    st.session_state.current_index = 0

if "annotator_name" not in st.session_state:
    st.session_state.annotator_name = ""

if "root_directory" not in st.session_state:
    st.session_state.root_directory = ""

if "started" not in st.session_state:
    st.session_state.started = False

if "images_data" not in st.session_state:
    st.session_state.images_data = []

if "auto_save_enabled" not in st.session_state:
    st.session_state.auto_save_enabled = True

# ==================== CSS ====================

st.markdown("""
<style>
.image-container {
    border: 2px solid #e0e0e0;
    border-radius: 8px;
    padding: 10px;
    margin: 10px 0;
    background-color: #fafafa;
}
.image-title {
    font-size: 0.9rem;
    font-weight: 600;
    color: #424242;
    margin-bottom: 8px;
    text-align: center;
}
.badge-label {
    display: inline-block;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 0.85rem;
    font-weight: 600;
    margin: 5px;
}
.badge-initial {
    background-color: #e3f2fd;
    color: #1976d2;
}
.badge-selected {
    background-color: #e8f5e9;
    color: #2e7d32;
}
</style>
""", unsafe_allow_html=True)

# ==================== INTERFACE PRINCIPALE ====================

st.title("🖼️ Ajout des échantillons de classification des fissures.")
st.markdown("---")

# ==================== ÉCRAN DE DÉMARRAGE ====================

if not st.session_state.started:
    st.markdown("""
    ### Bienvenue dans l'outil de sélection d'images
    
    Cet outil vous permet de sélectionner la classe de l’imagette présentant la fissure en se basant sur le contexte, grâce à l’affichage de l’image originale avec le rectangle englobant la fissure.
    
    **Fonctionnalités:**
    - ✅ Affichage côte à côte des images bbox et crop
    - 🏷️ Sélection du label approprié parmi les classes prédéfinies
    - 💾 Sauvegarde automatique de la progression
    - 📧 Notification par email à la fin de la sélection
    - ⏯️ Possibilité de reprendre une session en cours
    """)
    
    tab1, tab2 = st.tabs(["📝 Nouvelle sélection", "📂 Reprendre une session"])
    
    with tab1:
        st.markdown("#### Démarrer une nouvelle session de sélection d'images")
        
        name = st.text_input("👤 Votre nom/prénom:", key="name_input_new")
        root_dir = st.text_input(
            "📁 Chemin du dossier principal contenant les sous-dossiers d'images:",
            placeholder="Ex: ./images_a_annoter",
            key="root_dir_input"
        )
        
        if st.button("🚀 Démarrer l'annotation", type="primary", key="start_new"):
            if not name.strip():
                st.error("⚠️ Veuillez entrer votre nom")
            elif not root_dir.strip():
                st.error("⚠️ Veuillez spécifier le dossier principal")
            elif not os.path.exists(root_dir.strip()):
                st.error(f"⚠️ Le dossier '{root_dir.strip()}' n'existe pas")
            else:
                # Vérifier si une sauvegarde existe
                save_data, msg = load_progress(name.strip())
                if save_data:
                    st.warning(f"⚠️ Une sauvegarde existe pour '{name.strip()}' ({save_data.get('current_index', 0)}/{save_data.get('total_images', 0)} images)")
                    st.info("💡 Utilisez l'onglet 'Reprendre une session' ou choisissez un autre nom")
                else:
                    # Scanner les images
                    with st.spinner("🔍 Analyse du dossier en cours..."):
                        images_data = scan_images_directory(root_dir.strip())
                    
                    if not images_data:
                        st.error("❌ Aucune paire d'images bbox/crop trouvée dans ce dossier")
                    else:
                        st.session_state.annotator_name = name.strip()
                        st.session_state.root_directory = root_dir.strip()
                        st.session_state.images_data = images_data
                        st.session_state.current_index = 0
                        initialize_session(images_data)
                        st.session_state.started = True
                        st.success(f"✅ {len(images_data)} paires d'images trouvées!")
                        st.rerun()
    
    with tab2:
        st.markdown("#### Reprendre une session sauvegardée")
        
        saved_sessions = list_saved_sessions()
        
        if saved_sessions:
            st.markdown(f"**{len(saved_sessions)} session(s) sauvegardée(s):**")
            
            for session in saved_sessions:
                with st.expander(f"👤 {session['annotateur']} - {session['progression']}"):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"📊 Progression: {session['progression']}")
                        st.write(f"🕒 Date: {session['date']}")
                        st.write(f"📁 Dossier: {session['root_directory']}")
                    with col2:
                        if st.button("▶️ Reprendre", key=f"load_{session['filename']}"):
                            save_data, msg = load_progress(session['annotateur'])
                            if save_data:
                                # Recharger les images
                                with st.spinner("🔍 Rechargement des images..."):
                                    images_data = scan_images_directory(save_data['root_directory'])
                                
                                if images_data:
                                    st.session_state.annotator_name = save_data['annotateur']
                                    st.session_state.root_directory = save_data['root_directory']
                                    st.session_state.current_index = save_data['current_index']
                                    st.session_state.responses = save_data['responses']
                                    st.session_state.images_data = images_data
                                    st.session_state.started = True
                                    st.success("✅ Session chargée!")
                                    st.rerun()
                                else:
                                    st.error("❌ Impossible de recharger les images du dossier")
                            else:
                                st.error(msg)
        else:
            st.info("📭 Aucune session sauvegardée trouvée")

# ==================== INTERFACE D'ANNOTATION ====================

else:
    images_data = st.session_state.images_data
    idx = st.session_state.current_index
    
    # Sidebar avec contrôles
    with st.sidebar:
        st.markdown("### 💾 Sauvegarde")
        st.markdown(f"**👤 Annotateur:** {st.session_state.annotator_name}")
        st.markdown(f"**📊 Progression:** {idx}/{len(images_data)}")
        
        if st.button("💾 Sauvegarder maintenant", width='stretch'):
            success, msg = save_progress(images_data)
            if success:
                st.success(msg)
            else:
                st.error(msg)
        
        st.markdown("---")
        
        auto_save = st.checkbox(
            "Sauvegarde auto (toutes les 5 images)",
            value=st.session_state.auto_save_enabled
        )
        st.session_state.auto_save_enabled = auto_save
        
        if st.button("🏠 Retour à l'accueil", width='stretch'):
            if st.session_state.auto_save_enabled:
                save_progress(images_data)
            reset_session()
            st.rerun()
        
        st.markdown("---")
        st.markdown("### 📈 Statistiques")
        completed = sum(1 for r in st.session_state.responses.values() if r.get("label_choisi"))
        st.metric("Complétées", f"{completed}/{len(images_data)}")
        st.progress(completed / len(images_data))
    
    # Vérifier si terminé
    if idx >= len(images_data):
        st.success("🎉 **Annotation terminée !**")
        st.balloons()
        
        # Exporter les résultats
        csv_content = export_to_csv(images_data)
        
        # Envoyer l'email
        with st.spinner("📧 Envoi de la notification..."):
            success, message = send_completion_email(
                st.session_state.annotator_name,
                images_data,
                csv_content
            )
        
        if success:
            st.success(message)
            # Supprimer la sauvegarde temporaire
            try:
                filepath = get_save_filepath(st.session_state.annotator_name)
                if os.path.exists(filepath):
                    os.remove(filepath)
            except:
                pass
        else:
            st.error(message)
        
        # Résumé
        with st.expander("📊 Résumé des annotations", expanded=True):
            df = pd.DataFrame([
                {
                    "Image": img["bbox_file"],
                    "Dossier": img["folder"],
                    "Label initial": img["label_initial"],
                    "Label choisi": st.session_state.responses[i]["label_choisi"]
                }
                for i, img in enumerate(images_data)
            ])
            st.dataframe(df, width='stretch')
        
        # Téléchargement
        st.download_button(
            label="📥 Télécharger les résultats (CSV)",
            data=csv_content,
            file_name=f"annotations_{st.session_state.annotator_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            width='stretch'
        )
        
        if st.button("🔄 Nouvelle annotation", width='stretch'):
            reset_session()
            st.rerun()
    
    else:
        img_data = images_data[idx]
        
        # Barre de progression
        st.progress(idx / len(images_data))
        st.markdown(f"### Image {idx + 1} / {len(images_data)}")
        
        # Badge du dossier source
        st.markdown(f"""
        <div>
            <span class='badge-label badge-initial'>📁 Dossier: {img_data['folder']}</span>
            <span class='badge-label badge-initial'>🏷️ Label initial: {img_data['label_initial']}</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Affichage des images côte à côte
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""<div class='image-container'>
                <div class='image-title'>🔳 Image BBOX</div>
            </div>""", unsafe_allow_html=True)
            
            if os.path.exists(img_data["bbox_path"]):
                img_bbox = Image.open(img_data["bbox_path"])
                st.image(img_bbox, width='stretch')
                st.caption(f"📄 {img_data['bbox_file']}")
            else:
                st.error("❌ Image bbox non trouvée")
        
        with col2:
            st.markdown("""<div class='image-container'>
                <div class='image-title'>✂️ Image CROP</div>
            </div>""", unsafe_allow_html=True)
            
            if os.path.exists(img_data["crop_path"]):
                img_crop = Image.open(img_data["crop_path"])
                st.image(img_crop, width='content')
                st.caption(f"📄 {img_data['crop_file']}")
            else:
                st.error("❌ Image crop non trouvée")
        
        st.markdown("---")
        
        # Zone d'annotation
        st.markdown("### ✏️ Annotation")
        
        current_choice = st.session_state.responses[idx]["label_choisi"]
        default_index = CLASSES_DISPONIBLES.index(current_choice) if current_choice in CLASSES_DISPONIBLES else 0
        
        choice = st.radio(
            "🏷️ Sélectionnez le label approprié:",
            CLASSES_DISPONIBLES,
            index=default_index,
            key=f"label_{idx}",
            horizontal=True
        )
        
        st.session_state.responses[idx]["label_choisi"] = choice
        
        comment = st.text_area(
            "💬 Commentaire (optionnel):",
            value=st.session_state.responses[idx]["commentaire"],
            key=f"comment_{idx}",
            height=100,
            placeholder="Ajoutez un commentaire si nécessaire..."
        )
        
        st.session_state.responses[idx]["commentaire"] = comment
        
        st.markdown("---")
        
        # Navigation
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col1:
            if st.button("⬅️ Précédent", disabled=(idx == 0), width='stretch'):
                st.session_state.current_index -= 1
                st.rerun()
        
        with col3:
            button_label = "Suivant ➡️" if idx < len(images_data) - 1 else "✅ Terminer"
            if st.button(button_label, type="primary", width='stretch'):
                st.session_state.current_index += 1
                
                # Sauvegarde automatique
                if st.session_state.auto_save_enabled and (st.session_state.current_index % 5 == 0):
                    success, msg = save_progress(images_data)
                    if success:
                        st.toast("💾 Sauvegarde automatique", icon="✅")
                
                st.rerun()

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 0.8rem;'>
    Outil d'annotation bbox/crop | Développé par Houda MAAMATOU
</div>
""", unsafe_allow_html=True)
