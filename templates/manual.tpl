% include('templates/header.tpl', title='Series')

<form method="post" action="/testing/report/{{series['message-id']}}">
    <div class="well">
        <h3>Report test result for</h3>
        <h4>{{series['subject']}}</h4>
        %for i in series['patches']:
            %if i['message-id'] != series['message-id']:
                <h4>{{i['subject']}}</h4>
            %end
        %end
    </div>
    <br>
    Log:
    <textarea class="form-control" name="log" rows="10"></textarea>
    <input type="hidden" name="manual" value="true" />
    <button type="submit" class="btn btn-success" name="passed" value="true">Pass</button>
    <button type="submit" class="btn btn-danger" name="passed" value="false">Fail</button>
</form>

% include('templates/footer.tpl')
