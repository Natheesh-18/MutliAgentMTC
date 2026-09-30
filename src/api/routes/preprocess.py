from fastapi import APIRouter
from src.api.runtime import *  # noqa: F401,F403
import os , uuid 
router = APIRouter()


@router.post("/data-preprocess")
async def preprocess(
    payload: DataPreprocessRequest,
    request: Request,
    projectid: Optional[str] = Header(None, alias="Projectid"),
    projectname: Optional[str] = Header(None, alias="Projectname"),
    projecttype: Optional[str] = Header(None, alias="Projecttype"),
    licensetype: Optional[str] = Header(None, alias="Licensetype"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    logger.info("=== Files PreProcess request received ===")

    try:
        # ---- Extract payload & headers ----
        license_id = payload.license_id
        file_names = payload.file_name
        file_ids = payload.file_id
        storage_type = payload.storageType or "cloudS3"
        if isinstance(storage_type, list) and len(storage_type) > 0:
            storage_type = storage_type[0]
        replace = payload.replace

        env = os.getenv("PROFILE")
        bucket_name = os.getenv("BUCKET_NAME")
        api_key = os.getenv("GROQ_API_KEY")
        model_name = "openai/gpt-oss-20b"
        service_provider = "DefaultGroq"

        project_id = projectid or request.headers.get("projectid")
        project_name = projectname or request.headers.get("projectname")
        project_type = projecttype or request.headers.get("projecttype")
        license_type = licensetype or request.headers.get("licensetype")
        bearer_token = authorization or request.headers.get("authorization")

        logger.info(f"file_names received: {file_names}")

    except Exception as e:
        logger.exception("Error parsing preprocess request")
        raise HTTPException(status_code=500, detail=str(e))

    # ---- Validate required parameters ----
    if not license_id or not project_id or not file_names:
        logger.warning("Missing required parameters: license_id, project_id, or file_name")
        return JSONResponse(
            status_code=200,
            content={
                "status": "failure",
                "responseCode": 400,
                "message": "Missing required parameters: license_id, project_id, or file_name."
            }
        )

    # ---- Normalize file_names ----
    file_names, error = normalizeFilesName(file_names)
    if error:
        logger.warning(f"Invalid file_name type: {type(payload.file_name)}")
        return JSONResponse(status_code=200, content=error)

    # ---- Init Qdrant collection ----
    collection_name = getCollectionName(env, license_id, project_id)
    logger.info(f"Initializing Qdrant collection: {collection_name}")
    init_collection(collection_name, qdrant_client)

    if replace:
        replace_result = delete_chunks_files(file_names, collection_name)
        logger.info(f"Replaced from qdrant: {replace_result}")
    else:
        logger.info("User expectation: First time to Process file")

    # ---- Choose fetch strategy ----
    if storage_type == "cloudS3":
        fetcher = S3FileFetcher(s3_client, bucket_name, license_id, project_id)
        file_id_map = {fn: None for fn in file_names}  # No file_ids needed for S3
    else:
        fetcher = ApiFileFetcher(bearer_token, license_type, project_id, project_name, project_type)
        if not file_ids or len(file_ids) != len(file_names):
            return JSONResponse(
                status_code=200,
                content={
                    "status": "failure",
                    "responseCode": 400,
                    "message": "file_ids must be provided and match the number of file_names for non-S3 storage."
                }
            )
        file_id_map = dict(zip(file_names, file_ids))

    # ---- Process each file ----
    responses = []

    for file_name in file_names:
        file_name = file_name.strip()
        logger.info(f"--- Processing file: {file_name} ---")
        # ---- Validate file extension ----
        ext_error = validateFileExtension(file_name)
        if ext_error:
            logger.warning(f"Unsupported file type for file: {file_name}")
            responses.append({"file": file_name, "status": "FAILED", "message": ext_error})
            updateMongodbStatus(env, license_id, project_id, file_name, "Failed")
            continue
        
        # ---- Check if file already exists in Qdrant ----
        summary_id = getSummaryId(collection_name)
        existing = qdrant_client.retrieve(collection_name=collection_name, ids=[summary_id])
        if existing:
            files_list = existing[0].payload.get("files", [])
            if any(f["fileName"] == file_name for f in files_list):
                logger.warning(f"File already exists in collection, skipping: {file_name}")
                responses.append({
                    "file": file_name,
                    "status": "FAILED",
                    "message": "File already exists"
                })
                updateMongodbStatus(env, license_id, project_id, file_name, "Failed")
                continue

        # ---- Fetch file bytes ----
        try:
            file_bytes = await fetcher.fetch(file_name, file_id=file_id_map.get(file_name))
             # ---- Set status to Processing ----
            logger.info(f"--- Processing file: {file_name} ---")
            updateMongodbStatus(env, license_id, project_id, file_name, "Processing")
        except Exception as e:
            logger.error(f"Failed to fetch file '{file_name}': {e}")
            responses.append({
                "file": file_name,
                "status": "FAILED",
                "message": str(e) if "upload a valid file" in str(e) else "File not found in S3"
            })
            updateMongodbStatus(env, license_id, project_id, file_name, "Failed")
            continue

        # ---- Run unified processing pipeline ----
        result = await processSingleFile(
            file_name=file_name,
            file_bytes=file_bytes,
            collection_name=collection_name,
            env=env,
            license_id=license_id,
            project_id=project_id,
            api_key=api_key,
            model_name=model_name,
            service_provider=service_provider,
        )
        responses.append(result)

    # ---- Final Summary ----
    total = len(responses)
    success = sum(1 for r in responses if r["status"] == "SUCCESS")
    failed = sum(1 for r in responses if r["status"] == "FAILED")

    logger.info("=== Files Info ===")
    logger.info(f"  |- Total files : {total}")
    logger.info(f"  |- Success     : {success}")
    logger.info(f"  |- Failed      : {failed}")
    for r in responses:
        logger.info(f"  |- [{r['status']}] {r['file']} → {r['message']}")
    logger.info("=== File PreProcess completed ===")

    # ---- Build Final Response ----
    failed_files = [r["file"] for r in responses if r["status"] == "FAILED"]
    success_files = [r["file"] for r in responses if r["status"] == "SUCCESS"]

    all_already_exist = responses and all(r["message"] == "File already exists" for r in responses)

    if all_already_exist:
        final_message = "File already exists" if len(responses) == 1 else "Files already exist"
        response_code = 400
    elif len(failed_files) == 0:
        final_message = "File is processed successfully" if len(success_files) == 1 else "Files are processed successfully"
        response_code = 200
    else:
        if len(success_files) == 0:
            final_message = "Unable to process the uploaded file. Please upload a valid file"
        else:
            final_message = (
                f"Unable to process the uploaded file. Please upload a valid file. "
                f"Successfully processed: {', '.join(success_files)}"
            )
        response_code = 500

    return JSONResponse(
        status_code=200,
        content={
            "responseCode": response_code,
            "responseObject": responses,
            "message": final_message
        }
    )

@router.delete("/delete-chunks")
async def delete_chunks(request: DeleteChunksRequest):
    license_id = request.license_id
    project_id = request.project_id
    file_name = request.file_name
    env = os.getenv("PROFILE")
    if env :
        collection_name = f"ff_cloud_{env}_{license_id}_{project_id}"
    else: 
        collection_name = f"ff_cloud_{license_id}_{project_id}"
    
    logger.info(f"Received delete-chunks request for file '{file_name}', license_id '{license_id}', project_id '{project_id}', collection '{collection_name}'")
    SUMMARY_INDEX = -1

    try:
        # 1. DELETE REGULAR CHUNKS (0, 1, 2, 3...)
        # Based on your JSON, we match the top-level 'fileName' key
        file_chunk_filter = Filter(
            must=[
                FieldCondition(
                    key="fileName",  # Matches the key in your provided JSON
                    match=MatchValue(value=file_name)
                )
            ]
        )

        qdrant_client.delete(
            collection_name=collection_name,
            points_selector=file_chunk_filter
        )

        # 2. UPDATE GLOBAL SUMMARY (-1)
        # We find the one point where chunk_index is -1
        response = qdrant_client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="chunk_index", match=MatchValue(value=SUMMARY_INDEX))]
            ),
            limit=1,
            with_payload=True
        )

        if response[0]:
            summary_point = response[0][0]
            payload = summary_point.payload
            
            # Extract the 'files' list from the summary payload
            # In your earlier global summary JSON, 'files' was at the top level of the payload
            original_files = payload.get("files", [])
            
            # Filter out the specific file entry
            updated_files = [f for f in original_files if f.get("fileName") != file_name]
            
            # Only update if something actually changed
            if len(original_files) != len(updated_files):
                payload["files"] = updated_files
                payload["total_files"] = len(updated_files)

                # Overwrite the summary point with the cleaned list
                qdrant_client.overwrite_payload(
                    collection_name=collection_name,
                    payload=payload,
                    points=[summary_point.id]
                )

        logger.info(f"Successfully deleted all chunks for file '{file_name}' from collection '{collection_name}'")
        return JSONResponse(
            status_code=200,
            content={
                "status": "SUCCESS",
                "message": f"All chunks with file '{file_name}' deleted successfully from collection."
            }
        )

    except Exception as e:
        logger.exception(f"Unexpected error deleting chunks for file '{file_name}' from collection '{collection_name}'")
        return JSONResponse(
            status_code=500,
            content={
                "responseCode": 400,
                "status": "FAILURE",
                "message": f"Failed to delete chunks for file '{file_name}'",
                "error": str(e)
            }
        )


