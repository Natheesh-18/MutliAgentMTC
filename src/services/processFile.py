from src.api.runtime import *
from src.services.aiDataSrcService import *

async def processSingleFile(
    file_name: str,
    file_bytes: bytes,
    collection_name: str,
    env: Optional[str],
    license_id: str,
    project_id: str,
    api_key: str,
    model_name: str,
    service_provider: str,
) -> Dict[str, Any]:
    """
    Complete processing pipeline for a single file.
    Extracts modules → builds embeddings → upserts to Qdrant.
    Returns a response dict with status and message.
    """
    temp_path = None

    try:

        # ---- Extract modules ----
        # Use a unique temp JSON file to avoid race conditions
        output_json = f"extracted_modules_{uuid.uuid4().hex}.json"
        logger.info(f"Running process_document_to_modules on: {file_name}")
        extraction_result = process_document_to_modules(
            file_bytes,file_name, api_key, model_name, service_provider, output_json
        )

        # ---- Handle extraction errors ----
        if "error" in extraction_result:
            error_msg = extraction_result["error"]
            logger.error(f"Processing error for file '{file_name}': {error_msg}")
            updateMongodbStatus(env, license_id, project_id, file_name, "Failed")
            return {"file": file_name, "status": "FAILED", "message": error_msg}

        modules = extraction_result.get("modules", [])
        logger.info(f"Modules extracted: {len(modules)}")

        if not modules:
            logger.warning(f"No modules extracted from file: {file_name}")
            updateMongodbStatus(env, license_id, project_id, file_name, "Failed")
            return {"file": file_name, "status": "FAILED", "message": "No modules extracted"}

        # ---- Build texts to embed ----
        application_full_summary = ""
        application_full_purpose = ""
        texts_to_embed = []

        for m in modules:
            desc = m.get("metadata", {}).get("description")
            preconditions = m.get("metadata", {}).get("preConditions", [])

            if desc:
                application_full_summary += (
                    f"Module: {m.get('moduleName')}\n"
                    f"Description: {desc}\n"
                    f"Preconditions: {preconditions}\n\n"
                )
                application_full_purpose += (
                    f"Module: {m.get('moduleName')}\n"
                    f"Purpose: {desc}\n\n"
                )

            context = (
                f"Module: {m.get('moduleName')}. "
                f"Purpose: {desc}. "
                f"Steps: {' '.join(m.get('functionalFlow', []))}. "
                f"Criteria: {' '.join(m.get('acceptanceCriteria', []))}"
            )
            texts_to_embed.append(context)

        summary_index = len(texts_to_embed)
        texts_to_embed.append(
            f"Global Application Summary for {file_name}: {application_full_summary}"
        )
        logger.info(f"Total texts to embed (modules + summary): {len(texts_to_embed)}")

        # ---- Generate embeddings ----
        logger.info("Generating embeddings...")
        embeddings = manualTestCaseDoc.embeddings.embed_documents(texts_to_embed)
        logger.info(f"Embeddings generated, total: {len(embeddings)}")

        # ---- Build Qdrant points ----
        points = []
        for i, module in enumerate(modules):
            points.append(models.PointStruct(
                id=str(uuid.uuid4()),
                vector=embeddings[i],
                payload={
                    "chunk_index": i,
                    "fileName": file_name,
                    "moduleName": module.get("moduleName"),
                    "credential": module.get("credential"),
                    "functionalFlow": module.get("functionalFlow"),
                    "acceptanceCriteria": module.get("acceptanceCriteria"),
                    "metadata": module.get("metadata")
                }
            ))
        logger.info(f"Built {len(modules)} module points for Qdrant")

        # ---- Handle global summary point ----
        summary_id = getSummaryId(collection_name)
        logger.info(f"Checking existing global summary with id: {summary_id}")

        existing = qdrant_client.retrieve(
            collection_name=collection_name,
            ids=[summary_id]
        )

        new_file_entry = {
            "fileName": file_name,
            "full_description": application_full_summary,
            "purpose": application_full_purpose,
            "module_count": len(modules)
        }

        if existing:
            files_list = existing[0].payload.get("files", [])
            logger.info(f"Existing summary found with {len(files_list)} file(s)")

            if any(f["fileName"] == file_name for f in files_list):
                logger.warning(f"File already exists in collection: {file_name}")
                updateMongodbStatus(env, license_id, project_id, file_name, "Failed")
                return {"file": file_name, "status": "FAILED", "message": "File already exists"}

            files_list.append(new_file_entry)
            logger.info(f"Appended to existing summary. Total files: {len(files_list)}")
        else:
            logger.info("No existing global summary found, creating new one")
            files_list = [new_file_entry]

        summary_point = models.PointStruct(
            id=summary_id,
            vector=embeddings[summary_index],
            payload={
                "chunk_index": -1,
                "type": "application_summary",
                "moduleName": "Global Application Summary",
                "files": files_list,
                "total_files": len(files_list)
            }
        )
        points.append(summary_point)

        # ---- Upsert to Qdrant ----
        logger.info(f"Upserting {len(points)} points to collection: {collection_name}")
        qdrant_client.upsert(collection_name=collection_name, points=points)

        collection_info = qdrant_client.get_collection(collection_name=collection_name)
        logger.info(f"Upsert successful for file: {file_name}")
        logger.info(f"Collection '{collection_name}' now has {collection_info.points_count} total points")

        # ---- Update MongoDB status to Processed ----
        updateMongodbStatus(env, license_id, project_id, file_name, "Processed")

        return {
            "file": file_name,
            "status": "SUCCESS",
            "message": f"File stored in Qdrant successfully. Total points: {collection_info.points_count}"
        }

    except ClientError as e:
        logger.error(f"S3/API ClientError for file '{file_name}': {e}")
        updateMongodbStatus(env, license_id, project_id, file_name, "Failed")
        return {"file": file_name, "status": "FAILED", "message": "File not found in S3"}

    except Exception as e:
        logger.exception(f"Unexpected error while processing file '{file_name}': {e}")
        updateMongodbStatus(env, license_id, project_id, file_name, "Failed")
        return {"file": file_name, "status": "FAILED", "message": str(e)}

    # finally:
        # # ---- Cleanup temp file ----
        # if temp_path and os.path.exists(temp_path):
        #     os.remove(temp_path)
        #     logger.info(f"Temp file removed: {temp_path}")
