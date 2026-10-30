import java.io.IOException;
import java.io.ObjectInputStream;
import javax.servlet.http.HttpServletRequest;

public class ImportHandler {
    public Object read(HttpServletRequest request) throws IOException, ClassNotFoundException {
        ObjectInputStream in = new ObjectInputStream(request.getInputStream());
        return in.readObject();
    }
}
