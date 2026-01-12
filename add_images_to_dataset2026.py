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

# CORRECTION MAJEURE: Utiliser un chemin absolu pour les sauvegardes
# Cela garantit que les sauvegardes sont toujours au même endroit
SCRIPT_DIR = Path(__file__).parent.absolute() if '__file__' in globals() else Path.cwd()
SAVE_FOLDER = SCRIPT_DIR / "sauvegardes_annotations_images"

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

def auto_annotate_skipped_images(from_index, to_index, images_data):
    """
    Auto-annote les images sautées avec leur label initial
    """
    for i in range(from_index, to_index):
        if i < len(images_data):
            # Si l'image n'a pas déjà été annotée ou ignorée
            if not st.session_state.responses[i].get("annotated", False) and \
               not st.session_state.responses[i].get("ignored", False):
                # Utiliser le label initial
                st.session_state.responses[i]["label_choisi"] = images_data[i]["label_initial"]
                st.session_state.responses[i]["annotated"] = True
                st.session_state.responses[i]["commentaire"] = "Auto-annoté (saut d'image)"

def get_absolute_path(path_str):
    """Convertit un chemin en chemin absolu"""
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()

def scan_images_directory(root_dir):
    """
    Scanne le dossier racine et récupère toutes les paires d'images bbox/crop
    Retourne une liste de dictionnaires avec les informations des images
    """
    images_data = []
    
    # CORRECTION: Convertir en chemin absolu
    root_path = get_absolute_path(root_dir)
    
    if not root_path.exists():
        st.error(f"❌ Le dossier '{root_path}' n'existe pas!")
        return images_data
    
    # Parcourir tous les sous-dossiers
    for subdir in sorted(os.listdir(root_path)):
        subdir_path = root_path / subdir
        
        if not subdir_path.is_dir():
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
                    "bbox_path": str(subdir_path / files["bbox"]),
                    "crop_path": str(subdir_path / files["crop"])
                })
    
    return images_data

def initialize_session(images_data):
    """Initialise les réponses pour toutes les images"""
    if "responses" not in st.session_state:
        st.session_state.responses = {}
    
    for i, img_data in enumerate(images_data):
        if i not in st.session_state.responses:
            st.session_state.responses[i] = {
                "label_choisi": None,
                "commentaire": "",
                "annotated": False,
                "ignored": False
            }

def get_save_filepath(annotator_name):
    """Génère le chemin du fichier de sauvegarde"""
    # CORRECTION: Créer le dossier s'il n'existe pas
    SAVE_FOLDER.mkdir(parents=True, exist_ok=True)
    
    safe_name = "".join(c for c in annotator_name if c.isalnum() or c in (' ', '_')).strip()
    safe_name = safe_name.replace(' ', '_')
    
    filepath = SAVE_FOLDER / f"sauvegarde_{safe_name}.json"
    return filepath

def save_progress(images_data):
    """Sauvegarde la progression actuelle"""
    if not st.session_state.annotator_name:
        return False, "Nom d'annotateur manquant"
    
    # CORRECTION: Sauvegarder le chemin absolu du dossier
    save_data = {
        "annotateur": st.session_state.annotator_name,
        "root_directory": st.session_state.root_directory,
        "root_directory_absolute": str(get_absolute_path(st.session_state.root_directory)),
        "date_sauvegarde": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "current_index": st.session_state.current_index,
        "responses": st.session_state.responses,
        "total_images": len(images_data),
        "version": "2.0"
    }
    
    filepath = get_save_filepath(st.session_state.annotator_name)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        return True, f"✅ Sauvegarde réussie dans {filepath}"
    except Exception as e:
        return False, f"❌ Erreur: {str(e)}"

def load_progress(annotator_name):
    """Charge une sauvegarde existante"""
    filepath = get_save_filepath(annotator_name)
    
    if not filepath.exists():
        return None, "Aucune sauvegarde trouvée"
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            save_data = json.load(f)
        
        # Convertir les clés en int
        if 'responses' in save_data:
            save_data['responses'] = {
                int(k): v for k, v in save_data['responses'].items()
            }
        
        # CORRECTION: Utiliser le chemin absolu si disponible
        if 'root_directory_absolute' in save_data:
            save_data['root_directory'] = save_data['root_directory_absolute']
        
        return save_data, "✅ Sauvegarde chargée"
    except Exception as e:
        return None, f"❌ Erreur: {str(e)}"

def list_saved_sessions():
    """Liste toutes les sessions sauvegardées"""
    # CORRECTION: Créer le dossier s'il n'existe pas
    SAVE_FOLDER.mkdir(parents=True, exist_ok=True)
    
    saves = []
    for filepath in SAVE_FOLDER.glob("sauvegarde_*.json"):
																			 
														  
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Utiliser le chemin absolu si disponible
                root_dir = data.get('root_directory_absolute', data.get('root_directory', ''))
                
                saves.append({
                    'annotateur': data.get('annotateur', 'Inconnu'),
                    'date': data.get('date_sauvegarde', 'Inconnue'),
                    'progression': f"{data.get('current_index', 0)}/{data.get('total_images', 0)}",
                    'filename': filepath.name,
                    'root_directory': root_dir,
                    'filepath': str(filepath)
                })
        except Exception as e:
            st.warning(f"⚠️ Impossible de lire {filepath.name}: {e}")
            continue
    
    # Trier par date (plus récent en premier)
    saves.sort(key=lambda x: x['date'], reverse=True)
    return saves

def export_to_csv(images_data, only_annotated=False):
    """
    Exporte les annotations au format CSV
    
    Args:
        images_data: Liste des données d'images
        only_annotated: Si True, exporte uniquement les images annotées/ignorées
    """
    results = []
    for i, img_data in enumerate(images_data):
        response = st.session_state.responses.get(i, {})
        ignored = response.get("ignored", False)
        annotated = response.get("annotated", False)
        label = response.get("label_choisi", "")
        
        # Si only_annotated=True, sauter les images non traitées
        if only_annotated and not annotated and not ignored:
            continue
        
        results.append({
            "image_bbox": img_data["bbox_file"],
            "image_crop": img_data["crop_file"],
            "dossier_source": img_data["folder"],
            "label_initial": img_data["label_initial"],
            "label_choisi": "IGNORÉ" if ignored else label,
            "statut": "Ignoré" if ignored else ("Annoté" if annotated else "Non annoté"),
            "commentaire": response.get("commentaire", ""),
            "annotated": annotated
        })
    
    df = pd.DataFrame(results)
    return df.to_csv(index=False).encode('utf-8')

def send_completion_email(annotator_name, images_data, csv_content, is_partial=False):
    """
    Envoie un email de notification
    
    Args:
        annotator_name: Nom de l'annotateur
        images_data: Liste des images
        csv_content: Contenu CSV à envoyer
        is_partial: True si c'est un envoi partiel, False si c'est la fin
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_CONFIG["sender"]
        msg['To'] = SMTP_CONFIG["receiver"]
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        subject_prefix = "📤 Annotations partielles" if is_partial else "✅ Annotation terminée"
        msg['Subject'] = f"{subject_prefix} - {annotator_name} - {timestamp}"
        
        completed = sum(1 for r in st.session_state.responses.values() if r.get("annotated", False))
        ignored = sum(1 for r in st.session_state.responses.values() if r.get("ignored", False))
        
        status_text = "partielles" if is_partial else "finales"
        
        body = f"""
Bonjour,

L'annotateur {annotator_name} a envoyé ses annotations {status_text}.

📊 Statistiques:
- Total d'images dans le projet: {len(images_data)}
- Images annotées: {completed}
- Images ignorées: {ignored}
- Date d'envoi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Dossier source: {st.session_state.root_directory}
- Type d'envoi: {"Partiel (en cours)" if is_partial else "Final (terminé)"}

Les résultats {'annotés jusqu\'à présent' if is_partial else 'finaux'} sont disponibles en pièce jointe au format CSV.

Cordialement,
Système d'annotation automatique
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Ajouter le CSV en pièce jointe avec timestamp
        csv_attachment = MIMEBase('application', 'octet-stream')
        csv_attachment.set_payload(csv_content)
        encoders.encode_base64(csv_attachment)
        
        filename_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_type = "partiel" if is_partial else "final"
        csv_attachment.add_header(
            'Content-Disposition',
            f'attachment; filename=annotations_{annotator_name}_{filename_type}_{filename_timestamp}.csv'
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

def count_completed_annotations():
    """Compte le nombre d'annotations réellement effectuées"""
    return sum(1 for r in st.session_state.responses.values() if r.get("annotated", False))

def count_ignored_images():
    """Compte le nombre d'images ignorées"""
    return sum(1 for r in st.session_state.responses.values() if r.get("ignored", False))

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

if "show_crop_zoom" not in st.session_state:
    st.session_state.show_crop_zoom = {}

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
.badge-pending {
    background-color: #fff3e0;
    color: #e65100;
}
.badge-ignored {
    background-color: #ffebee;
    color: #c62828;
}
.ignore-section {
    border: 2px dashed #ef5350;
    border-radius: 8px;
    padding: 15px;
    margin: 15px 0;
    background-color: #fff8f8;
}
.save-location {
    background-color: #f5f5f5;
    padding: 10px;
    border-radius: 5px;
    border-left: 4px solid #2196F3;
    margin: 10px 0;
    font-size: 0.85rem;
}
</style>
""", unsafe_allow_html=True)

# ==================== INTERFACE PRINCIPALE ====================

st.title("🖼️ Ajout des échantillons de classification des fissures.")
st.markdown("---")

# AFFICHER L'EMPLACEMENT DES SAUVEGARDES
with st.expander("ℹ️ Informations sur les sauvegardes - IMPORTANT"):
    st.markdown(f"""
    <div class='save-location'>
        <strong>📁 Emplacement des sauvegardes:</strong><br>
        <code>{SAVE_FOLDER}</code><br><br>
        <strong>💡 Conseil:</strong> Vos sauvegardes sont maintenant toujours stockées ici, 
        peu importe d'où vous lancez l'application!
    </div>
    """, unsafe_allow_html=True)
    
    if SAVE_FOLDER.exists():
        saves_count = len(list(SAVE_FOLDER.glob("sauvegarde_*.json")))
        st.success(f"✅ {saves_count} sauvegarde(s) trouvée(s) dans ce dossier")
    else:
        st.info("ℹ️ Le dossier de sauvegarde sera créé automatiquement à la première sauvegarde")

# ==================== ÉCRAN DE DÉMARRAGE ====================

if not st.session_state.started:
    st.markdown("""
    ### Bienvenue dans l'outil de sélection d'images
    
    Cet outil vous permet de sélectionner la classe de l'imagette présentant la fissure en se basant sur le contexte, grâce à l'affichage de l'image originale avec le rectangle englobant la fissure.
    
    **Fonctionnalités:**
    - ✅ Affichage côte à côte des images bbox et crop
    - 🔍 Zoom sur l'image crop
    - 🏷️ Sélection du label approprié parmi les classes prédéfinies
    - ❌ Option pour ignorer les images qui ne correspondent à aucune classe
    - 💾 **Sauvegarde persistante** (vos données sont conservées entre les sessions)
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
        
        # Aide pour le chemin
        if st.checkbox("📂 Aide : afficher le répertoire actuel"):
            st.code(f"Répertoire actuel : {Path.cwd()}")
            st.info("💡 Le chemin peut être absolu (ex: /home/user/dataset) ou relatif (ex: ./dataset)")
        
        if st.button("🚀 Démarrer l'annotation", type="primary", key="start_new"):
            if not name.strip():
                st.error("⚠️ Veuillez entrer votre nom")
            elif not root_dir.strip():
                st.error("⚠️ Veuillez spécifier le dossier principal")
            else:
                # Nettoyer et convertir en chemin absolu
                clean_path = root_dir.strip().replace(' /', '/').replace('/ ', '/')
                abs_path = get_absolute_path(clean_path)
                
                if not abs_path.exists():
                    st.error(f"⚠️ Le dossier '{abs_path}' n'existe pas")
                    st.info(f"💡 Vérifiez que le chemin est correct")
                else:
                    # Vérifier si une sauvegarde existe
                    save_data, msg = load_progress(name.strip())
                    if save_data:
                        st.warning(f"⚠️ Une sauvegarde existe pour '{name.strip()}' ({save_data.get('current_index', 0)}/{save_data.get('total_images', 0)} images)")
                        st.info("💡 Utilisez l'onglet 'Reprendre une session' ou choisissez un autre nom")
                    else:
                        # Scanner les images
                        with st.spinner("🔍 Analyse du dossier en cours..."):
                            images_data = scan_images_directory(str(abs_path))
                        
                        if not images_data:
                            st.error("❌ Aucune paire d'images bbox/crop trouvée dans ce dossier")
                            st.info("💡 Vérifiez que vos images se terminent par '_bbox' et '_crop'")
                        else:
                            st.session_state.annotator_name = name.strip()
                            st.session_state.root_directory = str(abs_path)
                            st.session_state.images_data = images_data
                            st.session_state.current_index = 0
                            initialize_session(images_data)
                            st.session_state.started = True
                            
                            # Afficher les sous-dossiers trouvés
                            folders = list(set(img["folder"] for img in images_data))
                            st.success(f"✅ {len(images_data)} paires d'images trouvées dans {len(folders)} sous-dossiers!")
                            with st.expander("📁 Sous-dossiers détectés"):
                                for folder in sorted(folders):
                                    count = sum(1 for img in images_data if img["folder"] == folder)
                                    st.write(f"- {folder}: {count} paires")
                            
                            st.info("💡 Si vous ajoutez des images pendant l'annotation, utilisez le bouton '🔄 Recharger les images' dans la sidebar")
                            
                            st.rerun()
    
    with tab2:
        st.markdown("#### Reprendre une session sauvegardée")
        
        saved_sessions = list_saved_sessions()
        
        if saved_sessions:
            st.markdown(f"**{len(saved_sessions)} session(s) sauvegardée(s):**")
            
            for session in saved_sessions:
                with st.expander(f"👤 {session['annotateur']} - {session['progression']} - {session['date']}"):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"📊 Progression: {session['progression']}")
                        st.write(f"🕒 Date: {session['date']}")
                        st.write(f"📁 Dossier: {session['root_directory']}")
                        st.caption(f"💾 Fichier: {session['filepath']}")
                    with col2:
                        if st.button("▶️ Reprendre", key=f"load_{session['filename']}"):
                            save_data, msg = load_progress(session['annotateur'])
                            if save_data:
                                # Vérifier que le dossier existe toujours
																				   
                                root_dir_path = get_absolute_path(save_data['root_directory'])
                                
                                if not root_dir_path.exists():
                                    st.error(f"❌ Le dossier source n'existe plus: {root_dir_path}")
                                    st.info("💡 Vérifiez que le dossier n'a pas été déplacé ou supprimé")
																							   
																					   
																			  
																   
																	   
											  
                                else:
                                    # Recharger les images
                                    with st.spinner("🔍 Rechargement des images..."):
                                        images_data = scan_images_directory(str(root_dir_path))
                                    
                                    if images_data:
                                        st.session_state.annotator_name = save_data['annotateur']
                                        st.session_state.root_directory = str(root_dir_path)
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
            st.markdown(f"**Emplacement de sauvegarde:** `{SAVE_FOLDER}`")

# ==================== INTERFACE D'ANNOTATION ====================

else:
    images_data = st.session_state.images_data
    idx = st.session_state.current_index
    
    # Sidebar avec contrôles
    with st.sidebar:
        st.markdown("### 💾 Sauvegarde")
        st.markdown(f"**👤 Annotateur:** {st.session_state.annotator_name}")
        st.markdown(f"**📊 Progression:** {idx}/{len(images_data)}")
        
        if st.button("💾 Sauvegarder maintenant", use_container_width=True):
            success, msg = save_progress(images_data)
            if success:
                st.success(msg)
            else:
                st.error(msg)
        
        st.markdown("---")
        
        # Bouton pour recharger les images
        if st.button("🔄 Recharger les images du dossier", use_container_width=True):
            with st.spinner("🔍 Rechargement en cours..."):
                # Sauvegarder d'abord
                save_progress(images_data)
                
                # Recharger les images
                new_images_data = scan_images_directory(st.session_state.root_directory)
                
                if new_images_data:
                    old_count = len(images_data)
                    new_count = len(new_images_data)
                    
                    # Mettre à jour la liste des images
                    st.session_state.images_data = new_images_data
                    
                    # Initialiser les réponses pour les nouvelles images
                    for i, img_data in enumerate(new_images_data):
                        if i not in st.session_state.responses:
                            st.session_state.responses[i] = {
                                "label_choisi": None,
                                "commentaire": "",
                                "annotated": False,
                                "ignored": False
                            }
                    
                    diff = new_count - old_count
                    if diff > 0:
                        st.success(f"✅ {diff} nouvelles images détectées! Total: {new_count}")
                    elif diff < 0:
                        st.warning(f"⚠️ {abs(diff)} images supprimées. Total: {new_count}")
                    else:
                        st.info(f"ℹ️ Aucun changement. Total: {new_count}")
                    
                    st.rerun()
                else:
                    st.error("❌ Aucune image trouvée")
        
        st.markdown("---")
        
        auto_save = st.checkbox(
            "Sauvegarde auto (toutes les 5 images)",
            value=st.session_state.auto_save_enabled
        )
        st.session_state.auto_save_enabled = auto_save
        
        if st.button("🏠 Retour à l'accueil", use_container_width=True):
            if st.session_state.auto_save_enabled:
                save_progress(images_data)
            reset_session()
            st.rerun()
        
        st.markdown("---")
        st.markdown("### 📈 Statistiques")
        completed = count_completed_annotations()
        ignored = count_ignored_images()
        st.metric("Annotées", f"{completed}/{len(images_data)}")
        st.metric("Ignorées", f"{ignored}/{len(images_data)}")
        total_processed = completed + ignored
        progress_pct = total_processed / len(images_data) if len(images_data) > 0 else 0
        st.progress(progress_pct)
        
        # Statistiques par sous-dossier
        with st.expander("📁 Par sous-dossier"):
            folders = {}
            for i, img in enumerate(images_data):
                folder = img["folder"]
                if folder not in folders:
                    folders[folder] = {"total": 0, "annotated": 0, "ignored": 0}
                folders[folder]["total"] += 1
                if st.session_state.responses[i].get("annotated", False):
                    folders[folder]["annotated"] += 1
                if st.session_state.responses[i].get("ignored", False):
                    folders[folder]["ignored"] += 1
            
            for folder in sorted(folders.keys()):
                stats = folders[folder]
                st.write(f"**{folder}:**")
                st.write(f"  ✅ Annotées: {stats['annotated']}/{stats['total']}")
                st.write(f"  ❌ Ignorées: {stats['ignored']}/{stats['total']}")

        
        st.markdown("---")
        st.markdown("### 🎯 Navigation rapide")

        current_value = min(idx + 1, len(images_data))
                
        # Input pour aller à une image spécifique
        target_image = st.number_input(
                    "Aller à l'image n°:",
                    min_value=1,
                    max_value=len(images_data),
                    value=current_value,
                    step=1,
                    key="target_image_input"
        )
                
        if st.button("🚀 Aller à cette image", use_container_width=True):
                    target_index = target_image - 1
                    
                    if target_index != idx:
                        # Auto-annoter les images sautées
                        if target_index > idx:
                            auto_annotate_skipped_images(idx, target_index, images_data)
                            skipped_count = target_index - idx
                            st.toast(f"✅ {skipped_count} image(s) auto-annotée(s) avec leur label initial", icon="🏷️")
                        
                        st.session_state.current_index = target_index
                        
                        # Sauvegarde automatique après le saut
                        if st.session_state.auto_save_enabled:
                            save_progress(images_data)
                        
                        st.rerun()
                
        st.markdown("---")
        st.markdown("### 📤 Envoi des annotations")
                
        annotated_count = count_completed_annotations()
        ignored_count = count_ignored_images()
        total_processed = annotated_count + ignored_count
                
        st.info(f"📊 {total_processed} image(s) prête(s) à être envoyée(s)")
                
        if st.button("📧 Envoyer les annotations actuelles", 
                            use_container_width=True,
                            type="secondary",
                            disabled=(total_processed == 0)):
                    if total_processed > 0:
                        with st.spinner("📧 Préparation et envoi en cours..."):
                            # Sauvegarder d'abord
                            save_progress(images_data)
                            
                            # Exporter seulement les images annotées/ignorées
                            csv_content = export_to_csv(images_data, only_annotated=True)
                            
                            # Envoyer l'email
                            success, message = send_completion_email(
                                st.session_state.annotator_name,
                                images_data,
                                csv_content,
                                is_partial=True  # C'est un envoi partiel
                            )
                            
                            if success:
                                st.success(message)
                                st.balloons()
                            else:
                                st.error(message)
                    else:
                        st.warning("⚠️ Aucune annotation à envoyer")
    
    # Vérifier si terminé
    if idx >= len(images_data):
        st.success("🎉 **Annotation terminée !**")
        st.balloons()
        
        # Exporter les résultats
        csv_content = export_to_csv(images_data, only_annotated=False)
        
        # Envoyer l'email
        with st.spinner("📧 Envoi de la notification..."):
            success, message = send_completion_email(
                st.session_state.annotator_name,
                images_data,
                csv_content,
                is_partial=False  # C'est l'envoi final
            )
        
        if success:
            st.success(message)
            # Supprimer la sauvegarde temporaire
            try:
                filepath = get_save_filepath(st.session_state.annotator_name)
                if filepath.exists():
                    filepath.unlink()
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
                    "Label choisi": "IGNORÉ" if st.session_state.responses[i].get("ignored", False) else (st.session_state.responses[i]["label_choisi"] or "Non annoté"),
                    "Statut": "❌ Ignoré" if st.session_state.responses[i].get("ignored", False) else ("✅ Annoté" if st.session_state.responses[i].get("annotated", False) else "⏳ Non annoté")
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
        
        # Statut de l'annotation actuelle
        is_ignored = st.session_state.responses[idx].get("ignored", False)
        is_annotated = st.session_state.responses[idx].get("annotated", False)
        is_auto_annotated = "Auto-annoté" in st.session_state.responses[idx].get("commentaire", "")
        
        if is_ignored:
            status_badge = "❌ Ignorée"
            status_class = "badge-ignored"
        elif is_auto_annotated:
            status_badge = "🤖 Auto-annotée"
            status_class = "badge-initial"
        elif is_annotated:
            status_badge = "✅ Annotée"
            status_class = "badge-selected"
        else:
            status_badge = "⏳ Non annotée"
            status_class = "badge-pending"
        
        # Badge du dossier source
        st.markdown(f"""
        <div>
            <span class='badge-label badge-initial'>📁 Dossier: {img_data['folder']}</span>
            <span class='badge-label badge-initial'>🏷️ Label initial: {img_data['label_initial']}</span>
            <span class='badge-label {status_class}'>{status_badge}</span>
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
                
                # Afficher l'image normalement
                st.image(img_crop, width='content')
                st.caption(f"📄 {img_data['crop_file']}")

                zoom_key = f"zoom_{idx}"
                
                if zoom_key not in st.session_state.show_crop_zoom:
                    st.session_state.show_crop_zoom[zoom_key] = False
                
                # Bouton pour zoomer avec colonnes pour centrer
                col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
                with col_btn2:
                    if st.button("🔍 Zoom", key=f"btn_zoom_{idx}", width='stretch'):
                        st.session_state.show_crop_zoom[zoom_key] = not st.session_state.show_crop_zoom[zoom_key]
                        st.rerun()
                
                # Afficher le modal de zoom si activé
                if st.session_state.show_crop_zoom[zoom_key]:
                    # Créer une section séparée pour le zoom
                    st.markdown("---")
                    st.markdown("### 🔍 Mode Zoom")
                    
                    # Bouton fermer en haut
                    if st.button("✕ Fermer le zoom", key=f"close_zoom_top_{idx}", type="primary", width='stretch'):
                        st.session_state.show_crop_zoom[zoom_key] = False
                        st.rerun()
                    
                    # Afficher l'image en grand
                    st.image(img_crop, width='stretch', caption="Image CROP agrandie")
                    
                    # Bouton fermer en bas aussi
                    if st.button("✕ Fermer le zoom", key=f"close_zoom_bottom_{idx}", type="secondary", width='stretch'):
                        st.session_state.show_crop_zoom[zoom_key] = False
                        st.rerun()
                    
                    st.markdown("---")
            else:
                st.error("❌ Image crop non trouvée")
        
        st.markdown("---")
        
        # Zone d'annotation
        st.markdown("### ✏️ Annotation")
        
        # **SECTION IGNORER** (NOUVEAU)
        st.markdown("<div class='ignore-section'>", unsafe_allow_html=True)
        
        ignore_checkbox = st.checkbox(
            "❌ **Ignorer cette image** (ne correspond à aucune des 4 classes)",
            value=is_ignored,
            key=f"ignore_{idx}",
            help="Cochez cette case si l'image ne correspond à aucune des classes disponibles"
        )
        
        if ignore_checkbox != is_ignored:
            st.session_state.responses[idx]["ignored"] = ignore_checkbox
            if ignore_checkbox:
                # Si on ignore, on efface le label et on marque comme non annoté
                st.session_state.responses[idx]["label_choisi"] = None
                st.session_state.responses[idx]["annotated"] = False
            st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        # SÉLECTION DU LABEL (désactivé si ignoré)
        if not ignore_checkbox:
            current_choice = st.session_state.responses[idx]["label_choisi"]
            
            # Si pas encore de choix, utiliser le label initial comme suggestion
            if current_choice is None:
                default_index = CLASSES_DISPONIBLES.index(img_data["label_initial"]) if img_data["label_initial"] in CLASSES_DISPONIBLES else 0
            else:
                default_index = CLASSES_DISPONIBLES.index(current_choice) if current_choice in CLASSES_DISPONIBLES else 0
            
            choice = st.radio(
                "🏷️ Sélectionnez le label approprié:",
                CLASSES_DISPONIBLES,
                index=default_index,
                key=f"label_{idx}",
                horizontal=True
            )
            
            # Marquer comme annoté si l'utilisateur change le choix
            if choice != current_choice:
                st.session_state.responses[idx]["label_choisi"] = choice
                st.session_state.responses[idx]["annotated"] = True
                st.session_state.responses[idx]["ignored"] = False
        else:
            st.info("ℹ️ Image ignorée - sélection de label désactivée")
        
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
                # Marquer comme annoté ou ignoré si pas déjà fait
                if not ignore_checkbox and not st.session_state.responses[idx].get("annotated", False):
                    st.session_state.responses[idx]["annotated"] = True
                    if st.session_state.responses[idx]["label_choisi"] is None:
                        # Utiliser le choix actuel du radio button si disponible
                        if not ignore_checkbox:
                            st.session_state.responses[idx]["label_choisi"] = CLASSES_DISPONIBLES[default_index]
                
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
    Outil d'annotation bbox/crop | Développé par Houda MAAMATOU & Claude
</div>
""", unsafe_allow_html=True)