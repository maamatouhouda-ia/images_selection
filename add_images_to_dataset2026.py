# Ajoutez ces lignes dans la section d'affichage de l'image crop (remplacez le bloc "with col2:")

        with col2:
            st.markdown("""<div class='image-container'>
                <div class='image-title'>✂️ Image CROP</div>
            </div>""", unsafe_allow_html=True)
            
            if os.path.exists(img_data["crop_path"]):
                img_crop = Image.open(img_data["crop_path"])
                
                # Afficher l'image normalement
                st.image(img_crop, use_container_width=True)
                st.caption(f"📄 {img_data['crop_file']}")
                
                # Bouton pour zoomer
                zoom_key = f"zoom_{idx}"
                if zoom_key not in st.session_state.show_crop_zoom:
                    st.session_state.show_crop_zoom[zoom_key] = False
                
                col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
                with col_btn2:
                    if st.button("🔍 Zoom", key=f"btn_zoom_{idx}", use_container_width=True):
                        st.session_state.show_crop_zoom[zoom_key] = not st.session_state.show_crop_zoom[zoom_key]
                        st.rerun()
                
                # Afficher l'overlay de zoom si activé
                if st.session_state.show_crop_zoom.get(zoom_key, False):
                    # Convertir l'image en base64
                    img_base64 = image_to_base64(img_crop)
                    
                    # Créer l'overlay HTML/JS
                    zoom_html = f"""
                    <div class="zoom-overlay" onclick="closeZoom_{idx}()">
                        <img src="{img_base64}" class="zoom-image" alt="Image zoomée">
                        <div style="position: absolute; top: 20px; right: 20px; color: white; font-size: 1.5rem; background: rgba(0,0,0,0.5); padding: 10px 20px; border-radius: 5px; cursor: pointer;">
                            ✕ Fermer (cliquez n'importe où)
                        </div>
                    </div>
                    <script>
                    function closeZoom_{idx}() {{
                        window.parent.postMessage({{type: 'streamlit:setComponentValue', value: 'close_zoom'}}, '*');
                    }}
                    </script>
                    """
                    st.components.v1.html(zoom_html, height=800, scrolling=False)
                    
                    # Fermer le zoom après affichage
                    if st.button("✕ Fermer le zoom", key=f"close_zoom_{idx}", type="primary"):
                        st.session_state.show_crop_zoom[zoom_key] = False
                        st.rerun()
            else:
                st.error("❌ Image crop non trouvée")
