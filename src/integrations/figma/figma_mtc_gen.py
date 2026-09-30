from qdrant_client.models import Filter, FieldCondition,MatchValue
async def get_page_flow(page_name, collection_name,q_client,instance_name):
                    search_filter = Filter(
                        must=[
                            FieldCondition(
                                key="FlowName",
                                match=MatchValue(value=page_name)
                            ),
                            FieldCondition(
                                key="source",
                                match=MatchValue(value=instance_name)
                            )
                        ]
                    )
                    results, _ = await q_client.scroll(
                        collection_name=collection_name,
                        scroll_filter=search_filter,
                        with_payload=True,
                        limit=1
                    )
                    if results:
                        payload = results[0].payload or {}
                        return {
                                    "FlowSummary": payload.get("FlowSummary")
                                }
                    print(f"❌ No flow found for page: {page_name}")
                    return None



async def retrive_e2e(collection_name,page_name,q_client,instance_name):
    search_filter = Filter(
        must=[
            FieldCondition(
                key="entier_page_summary_page_name",
                match=MatchValue(value=page_name)
            ),
            FieldCondition(
                key="source",
                match=MatchValue(value=instance_name)
            )
        ]
    )
    results, _ = await q_client.scroll(
        collection_name=collection_name,
        scroll_filter=search_filter,
        with_payload=True,
        limit=1
    )

    if results:
        payload = results[0].payload or {}
        return payload.get("entier_page_summary")
    return None  


async def retrive_e2e_image(collection_name,page_name,q_client,instance_name):
                    search_filter = Filter(
                        must=[
                            FieldCondition(
                                key="individual_page_name_for_images",
                                match=MatchValue(value=page_name)
                            ),
                            FieldCondition(
                                key="source",
                                match=MatchValue(value=instance_name)
                            )
                        ]
                    )

                    results, _ = await q_client.scroll(
                        collection_name=collection_name,
                        scroll_filter=search_filter,
                        with_payload=True,
                        limit=1
                    )

                    if results:
                        payload = results[0].payload or {}
                        return payload.get("individual_page_image")
                    return None 


async def retrive_chunk(collection_name,page_name,image_name,q_client,instance_name):
                    search_filter = Filter(
                        must=[
                            FieldCondition(
                                key="image_name",
                                match=MatchValue(value=image_name)
                            ),
                            FieldCondition(
                                key="page_name",
                                match=MatchValue(value=page_name)
                            ),
                            FieldCondition(
                                key="source",
                                match=MatchValue(value=instance_name)
                            )
                        ]
                    )
                    results, _ = await q_client.scroll(
                        collection_name=collection_name,
                        scroll_filter=search_filter,
                        with_payload=True,
                        limit=1
                    )

                    if results:
                        return results[0].payload
                    return None



async def retrive_flow(collection_name,page_name,flow,q_client,instance_name):
    search_filter = Filter(
        must=[
            FieldCondition(
                key="individual_flow",
                match=MatchValue(value=flow)
            ),
            FieldCondition(
                key="individual_flow_page_name",
                match=MatchValue(value=page_name)
            ),
            FieldCondition(
                key="source",
                match=MatchValue(value=instance_name)
            )

        ]
    )
    results, _ = await q_client.scroll(
        collection_name=collection_name,
        scroll_filter=search_filter,
        with_payload=True,
        limit=1
    )
    if results:
        payload = results[0].payload or {}
        return payload.get("Individual_FlowSummary")
    return None