"""Local character TF-IDF + latent semantic analysis. No cloud embeddings."""
import json,sqlite3,time
from common import ROOT
def run():
    import numpy as np,joblib
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    from sklearn.preprocessing import normalize
    from threadpoolctl import threadpool_limits
    conn=sqlite3.connect(ROOT/'database/questions.sqlite')
    rows=conn.execute('SELECT question_id,stem FROM questions ORDER BY question_id').fetchall();conn.close()
    vectorizer=TfidfVectorizer(analyzer='char',ngram_range=(2,3),min_df=2,max_features=35000,sublinear_tf=True,dtype=np.float32)
    with threadpool_limits(limits=2):
        x=vectorizer.fit_transform([r[1] for r in rows])
        svd=TruncatedSVD(n_components=min(64,x.shape[0]-1,x.shape[1]-1),random_state=42,n_iter=5)
        vectors=normalize(svd.fit_transform(x)).astype(np.float32)
    joblib.dump({'vectorizer':vectorizer,'svd':svd,'ids':[r[0] for r in rows],'method':'character_tfidf_lsa64'},ROOT/'database/semantic_model.joblib',compress=3)
    np.save(ROOT/'database/semantic_vectors.npy',vectors)
    (ROOT/'reports/semantic_index.json').write_text(json.dumps({'method':'character TF-IDF + LSA; approximate semantic reference only','questions':len(rows),'features':x.shape[1],'dimensions':vectors.shape[1]},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Local LSA index ready',vectors.shape)
if __name__=='__main__':run()
