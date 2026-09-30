"""Local-file ingest and Qdrant collection helpers."""
from src.persistence._shared import *  # noqa: F401,F403


class QdrantDocumentsMixin:
    def ensure_qdrant_collection(self, license_id, project_id):
        collection_name = f"ff_cloud_{license_id}_{project_id}"
        """Checks if a Qdrant collection exists and ensures it's saved in MongoDB."""
        existing_entry = self.qdrant_collection.find_one(
            {"license_id": license_id, "project_id": project_id}
        )

        if existing_entry:
            return True

        collections = self.qdrant_client.get_collections()
        if collection_name in [col.name for col in collections.collections]:
            self.save_to_db(license_id, project_id, collection_name)
            return True

        self.qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
        print(f"Created new Qdrant collection: {collection_name}")

        self.save_to_db(license_id, project_id, collection_name)
        return False

    def save_to_db(self, license_id, project_id, collection_name):
        """Saves license ID and collection name to MongoDB."""
        data = {
            "license_id": license_id,
            "project_id": project_id,
            "collection_name": collection_name,
        }
        self.qdrant_collection.insert_one(data)
        print(f"Saved to MongoDB: {data}")

    def read_files_load_documents(self):
        """Loads CSV files from the directory."""
        directory = self.file_path
        print(f"Checking files in directory: {os.path.abspath(directory)}")
        loaded_documents = []

        files = [
            file
            for file in os.listdir(directory)
            if file.endswith((".csv", ".docx", ".xlsx"))
        ]
        if not files:
            print("No CSV files found!")

        for file in files:
            file_path = os.path.join(directory, file)
            if file.endswith(".csv"):
                loader = CSVLoader(file_path=file_path, encoding="ISO-8859-1")
                documents = loader.load()
                loaded_documents.extend(documents)

            elif file.endswith(".docx"):
                loader = UnstructuredWordDocumentLoader(file_path=file_path)
                documents = loader.load()
                loaded_documents.extend(documents)

            elif file.endswith(".xlsx"):
                print(f"Reading Excel file: {file}")
                try:
                    xl = pd.read_excel(file_path, sheet_name=None)
                    for sheet_name, df in xl.items():
                        text = df.to_string(index=False)
                        doc = Document(
                            page_content=text,
                            metadata={"file": file, "sheet": sheet_name},
                        )
                        loaded_documents.append(doc)
                except Exception as e:
                    print(f"Error reading Excel file {file}: {e}")
        return loaded_documents

    def split_documents(self, file_data):
        """Splits documents into smaller chunks and adds chunk_id for ordering."""
        # print("Splitting documents into chunks...")

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500, 
            chunk_overlap=100,
            separators=["\n\n", "\n", " "]
        )

        # Split each document individually
        final_documents = []
        for doc in file_data:
            chunks = text_splitter.split_text(doc.page_content)  # split_text returns list of strings
            for i, chunk_text in enumerate(chunks):
                # Copy existing metadata and add chunk_id
                metadata = doc.metadata.copy()
                metadata.update({
                    "chunk_id": i
                })
                final_documents.append(Document(page_content=chunk_text, metadata=metadata))

        return final_documents

    def vector_data_base(self, final_documents, license_id, project_id):
        """Stores document embeddings in Qdrant."""
        print("📡 Storing embeddings in Qdrant...")
        collection_name = f"ff_cloud_{license_id}_{project_id}"
        Qdrant.from_documents(
            final_documents,
            embedding=self.embeddings,
            url=f"{QDRANT_HOST}:{QDRANT_PORT}",
            collection_name=collection_name,
            prefer_grpc=False,
        )
        print(f"Data stored in Qdrant collection: {collection_name}")
